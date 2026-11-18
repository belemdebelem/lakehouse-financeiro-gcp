CREATE TABLE IF NOT EXISTS bronze.customers (
  customer_id STRING NOT NULL,
  customer_segment STRING NOT NULL,
  created_at DATE NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  batch_id STRING NOT NULL,
  source_file STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  ingestion_date DATE NOT NULL,
  PRIMARY KEY (customer_id) NOT ENFORCED
)
PARTITION BY ingestion_date
CLUSTER BY customer_segment;

CREATE TABLE IF NOT EXISTS bronze.contracts (
  contract_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  product_type STRING NOT NULL,
  principal_amount NUMERIC NOT NULL,
  annual_interest_rate NUMERIC NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  batch_id STRING NOT NULL,
  source_file STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  ingestion_date DATE NOT NULL,
  PRIMARY KEY (contract_id) NOT ENFORCED
)
PARTITION BY ingestion_date
CLUSTER BY product_type, status;

CREATE TABLE IF NOT EXISTS bronze.installments (
  contract_id STRING NOT NULL,
  installment_number INT64 NOT NULL,
  due_date DATE NOT NULL,
  paid_at DATE,
  amount_due NUMERIC NOT NULL,
  amount_paid NUMERIC NOT NULL,
  status STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  batch_id STRING NOT NULL,
  source_file STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  ingestion_date DATE NOT NULL,
  PRIMARY KEY (contract_id, installment_number) NOT ENFORCED
)
PARTITION BY ingestion_date
CLUSTER BY status;
