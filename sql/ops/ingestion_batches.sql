CREATE TABLE IF NOT EXISTS ops.ingestion_batches (
  batch_id STRING NOT NULL,
  entity STRING NOT NULL,
  source_file STRING NOT NULL,
  row_count INT64 NOT NULL,
  status STRING NOT NULL,
  error STRING,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  ingestion_date DATE NOT NULL,
  PRIMARY KEY (batch_id, entity) NOT ENFORCED
)
PARTITION BY ingestion_date
CLUSTER BY entity;
