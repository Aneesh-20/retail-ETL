-- Note: This script runs during the initial startup of the Postgres container under the default database.

-- Create databases
CREATE DATABASE retail_source;
CREATE DATABASE retail_warehouse;
CREATE DATABASE airflow;

-- Grant replication privileges to the default user so Debezium CDC can connect and read WAL logs.
ALTER ROLE retail_user WITH REPLICATION;
