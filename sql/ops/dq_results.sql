CREATE TABLE IF NOT EXISTS ops.dq_results (
  ingestion_date DATE NOT NULL,
  entity STRING NOT NULL,
  batch_id STRING NOT NULL,
  metric_name STRING NOT NULL,
  metric_value NUMERIC,
  status STRING NOT NULL,
  details STRING,
  checked_at TIMESTAMP NOT NULL,
  PRIMARY KEY (ingestion_date, entity, metric_name) NOT ENFORCED
)
PARTITION BY ingestion_date
CLUSTER BY entity, metric_name;
