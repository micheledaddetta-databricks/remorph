from sqlglot.dialects.presto import Presto as presto
from sqlglot import exp
from sqlglot.helper import seq_get
from sqlglot.errors import ParseError
from sqlglot.dialects.dialect import locate_to_strposition
from sqlglot.tokens import TokenType

from databricks.labs.remorph.snow import local_expression


def _build_approx_percentile(args: list) -> exp.Expression:
    if len(args) == 4:
        arg3 = seq_get(args, 3)
        try:
            number = float(arg3.this) if arg3 is not None else 0
            return exp.ApproxQuantile(
                this=seq_get(args, 0),
                weight=seq_get(args, 1),
                quantile=seq_get(args, 2),
                accuracy=exp.Literal(this=f'{int((1/number) * 100)} ', is_string=False),
            )
        except ValueError as exc:
            raise ParseError(f"Expected a string representation of a number for argument 2, but got {arg3}") from exc
    if len(args) == 3:
        arg2 = seq_get(args, 2)
        try:
            number = float(arg2.this) if arg2 is not None else 0
            return exp.ApproxQuantile(
                this=seq_get(args, 0),
                quantile=seq_get(args, 1),
                accuracy=exp.Literal(this=f'{int((1/number) * 100)}', is_string=False),
            )
        except ValueError as exc:
            raise ParseError(f"Expected a string representation of a number for argument 2, but got {arg2}") from exc
    return exp.ApproxQuantile.from_arg_list(args)


def _build_any_keys_match(args: list) -> local_expression.ArrayExists:
    return local_expression.ArrayExists(
        this=local_expression.MapKeys(this=seq_get(args, 0)), expression=seq_get(args, 1)
    )


class Presto(presto):

    class Parser(presto.Parser):
        VALUES_FOLLOWED_BY_PAREN = False

        FUNCTIONS = {
            **presto.Parser.FUNCTIONS,
            "APPROX_PERCENTILE": _build_approx_percentile,
            "STRPOS": locate_to_strposition,
            "ANY_KEYS_MATCH": _build_any_keys_match,
        }

    class Tokenizer(presto.Tokenizer):
        KEYWORDS = {
            **presto.Tokenizer.KEYWORDS,
            "JSON": TokenType.TEXT,
        }
