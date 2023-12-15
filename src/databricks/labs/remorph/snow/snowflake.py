import copy
import re
import typing as t
from typing import ClassVar

from sqlglot import exp
from sqlglot.dialects.snowflake import Snowflake
from sqlglot.errors import ParseError
from sqlglot.helper import seq_get
from sqlglot.tokens import Token, TokenType
from sqlglot.trie import new_trie

from databricks.labs.remorph.snow import local_expression


def _parse_dateadd(args: list) -> exp.DateAdd:
    return exp.DateAdd(this=seq_get(args, 2), expression=seq_get(args, 1), unit=seq_get(args, 0))


def _parse_trytonumber(args: list) -> local_expression.TryToNumber:
    if len(args) == 1 or len(args) == 3:
        msg = f"""Error Parsing args `{args}`:
                             * `format` is required
                             * `precision` and `scale` both are required [if specifed]
                          """
        raise ParseError(msg)

    if len(args) == 4:
        return local_expression.TryToNumber(
            this=seq_get(args, 0), expression=seq_get(args, 1), precision=seq_get(args, 2), scale=seq_get(args, 3)
        )

    return local_expression.TryToNumber(this=seq_get(args, 0), expression=seq_get(args, 1))


class Snow(Snowflake):
    # Instantiate Snowflake Dialect
    snowflake = Snowflake()

    class Tokenizer(snowflake.Tokenizer):
        IDENTIFIERS: ClassVar[list[str]] = ['"']

        COMMENTS: ClassVar[list[str]] = ["--", "//", ("/*", "*/")]
        STRING_ESCAPES: ClassVar[list[str]] = ["\\", "'"]

        CUSTOM_TOKEN_MAP: ClassVar[dict] = {
            r"(?i)CREATE\s+OR\s+REPLACE\s+PROCEDURE": TokenType.PROCEDURE,
            r"(?i)var\s+\w+\s+=\s+\w+?": TokenType.VAR,
        }

        KEYWORDS: ClassVar[dict] = {**Snowflake.Tokenizer.KEYWORDS}
        ## DEC is not a reserved keyword in Snowflake it can be used as table alias
        KEYWORDS.pop("DEC")

        @classmethod
        def update_keywords(cls, new_key_word_dict):
            cls.KEYWORDS = new_key_word_dict | cls.KEYWORDS

        @classmethod
        def merge_trie(cls, parent_trie, new_trie):
            merged_trie = {}
            # print(f"The Parent Trie is {parent_trie}")
            # print(f"The Input Trie is {new_trie}")
            for key in set(parent_trie.keys()) | set(new_trie.keys()):  # Get all unique keys from both tries
                if key in parent_trie and key in new_trie:  # If the key is in both tries, merge the subtries
                    if isinstance(parent_trie[key], dict) and isinstance(new_trie[key], dict):
                        # #print(f"New trie inside the key is {new_trie}")
                        # #print(f"Parent trie inside the key is {parent_trie}")
                        merged_trie[key] = cls.merge_trie(parent_trie[key], new_trie[key])
                        # #print(f"Merged Trie is {merged_trie}")
                    elif isinstance(parent_trie[key], dict):
                        merged_trie[key] = parent_trie[key]
                    else:
                        merged_trie[key] = new_trie[key]
                elif key in parent_trie:  # If the key is only in trie1, add it to the merged trie
                    merged_trie[key] = parent_trie[key]
                else:  # If the key is only in trie2, add it to the merged trie
                    merged_trie[key] = new_trie[key]
            return merged_trie

        @classmethod
        def update_keyword_trie(
            cls,
            new_trie,
            parent_trie=None,
        ):
            if parent_trie is None:
                parent_trie = cls._KEYWORD_TRIE
            cls.KEYWORD_TRIE = cls.merge_trie(parent_trie, new_trie)

        def match_strings_token_dict(self, string, pattern_dict):
            result_dict = {}
            for pattern in pattern_dict:
                matches = re.finditer(pattern, string, re.MULTILINE | re.IGNORECASE | re.DOTALL)
                for _, match in enumerate(matches, start=1):
                    result_dict[match.group().upper()] = pattern_dict[pattern]
            return result_dict

        def match_strings_list(self, string, pattern_dict):
            result = []
            for pattern in pattern_dict:
                matches = re.finditer(pattern, string, re.MULTILINE | re.IGNORECASE | re.DOTALL)
                for _, match in enumerate(matches, start=1):
                    result.append(match.group().upper())
            return result

        def tokenize(self, sql: str) -> list[Token]:
            """Returns a list of tokens corresponding to the SQL string `sql`."""
            self.reset()
            self.sql = sql
            ## Update Keywords
            ref_dict = self.match_strings_token_dict(sql, self.CUSTOM_TOKEN_MAP)
            self.update_keywords(ref_dict)
            ## Update Keyword Trie
            custom_trie = new_trie(self.match_strings_list(sql, self.CUSTOM_TOKEN_MAP))
            # print("**"*40)
            # print(f"The New Trie after adding the REF, VAR and IF ELSE
            # blocks basesd on {self.CUSTOM_TOKEN_MAP}, is \n\n {custom_trie}")
            # print("**"*40)
            self.update_keyword_trie(custom_trie)
            # print(f"Updated New Trie is {self.KEYWORD_TRIE}")
            # print("**"*40)
            ## Parent Code
            self.size = len(sql)
            try:
                self._scan()
            except Exception as e:
                start = self._current - 50
                end = self._current + 50
                start = start if start > 0 else 0
                end = end if end < self.size else self.size - 1
                context = self.sql[start:end]
                msg = f"Error tokenizing '{context}'"
                raise ParseError(msg) from e
            return self.tokens

    class Parser(snowflake.Parser):
        FUNCTIONS: ClassVar[dict] = {
            **Snowflake.Parser.FUNCTIONS,
            "STRTOK_TO_ARRAY": local_expression.Split.from_arg_list,
            "DATE_FROM_PARTS": local_expression.MakeDate.from_arg_list,
            "CONVERT_TIMEZONE": local_expression.ConvertTimeZone.from_arg_list,
            "TRY_TO_DATE": local_expression.TryToDate.from_arg_list,
            "STRTOK": local_expression.SplitPart.from_arg_list,
            "SPLIT_PART": local_expression.SplitPart.from_arg_list,
            "TIMESTAMPADD": _parse_dateadd,
            "TRY_TO_DECIMAL": _parse_trytonumber,
            "TRY_TO_NUMBER": _parse_trytonumber,
            "TRY_TO_NUMERIC": _parse_trytonumber,
        }

        FUNCTION_PARSERS: ClassVar[dict] = {
            **Snowflake.Parser.FUNCTION_PARSERS,
        }

        PLACEHOLDER_PARSERS: ClassVar[dict] = {
            **Snowflake.Parser.PLACEHOLDER_PARSERS,
            TokenType.PARAMETER: lambda self: self._parse_parameter(),
        }

        FUNC_TOKENS: ClassVar[dict] = {*Snowflake.Parser.FUNC_TOKENS, TokenType.COLLATE}

        COLUMN_OPERATORS: ClassVar[dict] = {
            **Snowflake.Parser.COLUMN_OPERATORS,
            TokenType.COLON: lambda self, this, path: self._json_column_op(this, path),
        }

        TIMESTAMPS: ClassVar[dict] = Snowflake.Parser.TIMESTAMPS.copy() - {TokenType.TIME}

        RANGE_PARSERS: ClassVar[dict] = {
            **Snowflake.Parser.RANGE_PARSERS,
        }

        ALTER_PARSERS: ClassVar[dict] = {**Snowflake.Parser.ALTER_PARSERS}

        def _parse_types(
            self, *, check_func: bool = False, schema: bool = False, allow_identifiers: bool = True
        ) -> t.Optional[exp.Expression]:  # noqa: UP007
            this = super()._parse_types(check_func=check_func, schema=schema, allow_identifiers=allow_identifiers)
            # https://docs.snowflake.com/en/sql-reference/data-types-numeric Numeric datatype alias
            if (
                isinstance(this, exp.DataType)
                and this.is_type("numeric", "decimal", "number", "integer", "int", "smallint", "bigint")
                and not this.expressions
            ):
                return exp.DataType.build("DECIMAL(38,0)")
            return this

        def _parse_parameter(self) -> local_expression.Parameter:
            wrapped = self._match(TokenType.L_BRACE)
            this = self._parse_var() or self._parse_identifier() or self._parse_primary()
            self._match(TokenType.R_BRACE)
            suffix = ""
            if not self._match(TokenType.SPACE) or self._match(TokenType.DOT):
                suffix = self._parse_var() or self._parse_identifier() or self._parse_primary()

            return self.expression(local_expression.Parameter, this=this, wrapped=wrapped, suffix=suffix)

        def _get_table_alias(self):
            """
            :returns the `table alias` by looping through all the tokens until it finds the `From` token.
            Example:
            * SELECT .... FROM persons p => returns `p`
            * SELECT
                 ....
              FROM
                 dwh.vw_replacement_customer  d  => returns `d`
            """
            self_copy = copy.deepcopy(self)
            found_from = True if self_copy._match(TokenType.FROM, advance=False) else False
            run = True
            indx = 0
            table_alias = None
            while run or found_from:
                self_copy._advance()
                indx += 1
                found_from = True if self_copy._match(TokenType.FROM, advance=False) else False
                if indx == len(self_copy._tokens):
                    run = False
                if found_from:
                    self_copy._advance(2)
                    table_alias = self_copy._curr.text
                    if table_alias == ".":
                        self_copy._advance(2)
                        table_alias = self_copy._curr.text
                    break
            return table_alias

        def _json_column_op(self, this, path):
            """
            Get the `table alias` using _get_table_alias() and it is used to check whether
            to remove `.value` from `<COL>.value`. We need to remove `.value` only if it refers
            to `Lateral View` alias.
            :return: the expression based on the alias.
            """
            table_alias = self._get_table_alias()

            if not isinstance(this, exp.Bracket) and this.name.upper() == "VALUE":
                if this.table != table_alias:
                    return self.expression(local_expression.Bracket, this=this.table, expressions=[path])
                return self.expression(local_expression.Bracket, this=this, expressions=[path])
            elif (isinstance(path, exp.Literal) and path.alias_or_name.upper() == "VALUE") or (
                isinstance(this, local_expression.Bracket)
                and (this.name.upper() == "VALUE" or this.this.table.upper() == table_alias.upper())
            ):
                return self.expression(local_expression.Bracket, this=this, expressions=[path])
            else:
                return self.expression(exp.Bracket, this=this, expressions=[path])