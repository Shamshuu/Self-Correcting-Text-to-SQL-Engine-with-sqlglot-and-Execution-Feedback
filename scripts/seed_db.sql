CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NULL, created_at DATE NOT NULL
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY, cust_id INTEGER NOT NULL REFERENCES customers(customer_id),
  order_date DATE NOT NULL, total_amount NUMERIC(12,2) NOT NULL, status TEXT NOT NULL
);
CREATE TABLE line_items (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), product_name TEXT NOT NULL,
  qty INTEGER NOT NULL, unit_price NUMERIC(12,2) NOT NULL
);
INSERT INTO customers(customer_id, name, region, created_at)
SELECT i, 'Customer ' || i, CASE WHEN i % 9 = 0 THEN NULL WHEN i % 3 = 0 THEN 'New York' WHEN i % 3 = 1 THEN 'West' ELSE 'South' END, DATE '2023-01-01' + (i % 365)
FROM generate_series(1, 120) AS i;
INSERT INTO orders(id, cust_id, order_date, total_amount, status)
SELECT i, ((i - 1) % 120) + 1, DATE '2024-01-01' + (i % 365), ((i % 9) + 1) * 25.50, CASE WHEN i % 11 = 0 THEN 'cancelled' ELSE 'completed' END
FROM generate_series(1, 600) AS i;
INSERT INTO line_items(id, order_id, product_name, qty, unit_price)
SELECT i, ((i - 1) / 3) + 1, 'Product ' || ((i % 20) + 1), ((i % 4) + 1), ((i % 9) + 1) * 8.50
FROM generate_series(1, 1800) AS i;
CREATE INDEX orders_cust_id_idx ON orders(cust_id);
CREATE INDEX line_items_order_id_idx ON line_items(order_id);
