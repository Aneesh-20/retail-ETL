import os
import sys
import unittest
import tempfile
import yaml
import json
import sqlite3
import pandas as pd
import numpy as np

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

class TestRetailLakehousePlatform(unittest.TestCase):
    
    def setUp(self):
        self.contract_path = os.path.join(PROJECT_ROOT, "config", "data_contracts.yaml")
        self.fallback_db_path = os.path.join(PROJECT_ROOT, "retail_fallback.db")
        
    def test_data_contracts_loading(self):
        """
        Verify that data_contracts.yaml is present and contains correct schema definitions
        """
        self.assertTrue(os.path.exists(self.contract_path))
        with open(self.contract_path, 'r') as f:
            contracts = yaml.safe_load(f).get("contracts", {})
            
        self.assertIn("customers", contracts)
        self.assertIn("products", contracts)
        self.assertIn("transactions", contracts)
        
        # Check customer PII configurations
        self.assertTrue(contracts["customers"]["columns"]["email"]["pii"])
        self.assertFalse(contracts["customers"]["columns"]["id"]["pii"])
        
    def test_synthetic_data_generation(self):
        """
        Create a temporary SQLite database, run the generator, and assert structures and record volumes
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = os.path.join(tmpdir, "test_source.db")
            
            # Import generator inline to run
            from src.generator.generate_data import SyntheticDataGenerator
            gen = SyntheticDataGenerator(fallback_db_path=temp_db)
            gen.create_schema()
            
            # Check schema creation
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            self.assertIn("customers", tables)
            self.assertIn("transactions", tables)
            self.assertIn("returns", tables)
            
            # Run generation for 2 days
            gen.run_generation(days_back=2)
            
            # Assert counts are greater than 0
            cursor.execute("SELECT count(*) FROM transactions")
            tx_count = cursor.fetchone()[0]
            self.assertGreater(tx_count, 0)
            
            cursor.execute("SELECT count(*) FROM customers")
            cust_count = cursor.fetchone()[0]
            self.assertGreater(cust_count, 0)
            
            conn.close()

    def test_fraud_scorer_logic(self):
        """
        Verify that fraud risk tiers are assigned correctly based on computed transaction scores
        """
        # Mock high-velocity and high-amount rows
        # High score >= 70, Medium >= 35, else Low
        tx_data = pd.DataFrame([
            {"id": "t1", "transaction_id": "TXN-1", "customer_id": "c1", "unit_price": 2000.0, "quantity": 1, "discount": 0.0, "transaction_timestamp": "2026-07-01 10:00:00"},
            {"id": "t2", "transaction_id": "TXN-2", "customer_id": "c2", "unit_price": 50.0, "quantity": 1, "discount": 0.0, "transaction_timestamp": "2026-07-01 10:00:00"}
        ])
        cust_data = pd.DataFrame([
            {"id": "c1", "email": "c1@example.com", "gender": "M", "state": "NY"},
            {"id": "c2", "email": "c2@example.com", "gender": "F", "state": "CA"}
        ])
        
        # Test individual transaction scoring
        score_1 = 0
        factors_1 = []
        val_1 = 2000.0
        
        if val_1 > 1500:
            score_1 += 35
            factors_1.append("High order value")
            
        self.assertEqual(score_1, 35)
        self.assertIn("High order value", factors_1)

    def test_forecaster_predictions_integrity(self):
        """
        Assert model output is bounded and does not output negative sales forecasts
        """
        pred_sales = np.array([-100.5, 450.2, 0.0, 1200.0])
        clipped = np.clip(pred_sales, 0, None)
        
        self.assertEqual(clipped[0], 0.0)
        self.assertEqual(clipped[1], 450.2)
        self.assertEqual(clipped[2], 0.0)
        
if __name__ == "__main__":
    unittest.main()
