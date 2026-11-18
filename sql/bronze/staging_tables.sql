CREATE TABLE IF NOT EXISTS bronze.customers_staging (
  customer_id STRING NOT NULL,
  customer_segment STRING NOT NULL,
  created_at DATE NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.contracts_staging (
  contract_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  product_type STRING NOT NULL,
  principal_amount NUMERIC NOT NULL,
  annual_interest_rate NUMERIC NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.installments_staging (
  contract_id STRING NOT NULL,
  installment_number INT64 NOT NULL,
  due_date DATE NOT NULL,
  paid_at DATE,
  amount_due NUMERIC NOT NULL,
  amount_paid NUMERIC NOT NULL,
  status STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
