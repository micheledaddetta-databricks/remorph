
-- snowflake sql:
!set exit_on_error = true;
SELECT !(2 = 2) AS always_false;


-- databricks sql:
-- snowsql command:!'set exit_on_error = true';
SELECT !(2 = 2) AS always_false