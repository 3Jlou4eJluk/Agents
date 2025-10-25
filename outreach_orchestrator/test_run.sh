#!/bin/bash

# Quick test run with 5 leads

echo "🧪 Running test with 5 leads from data/test_leads.csv"
echo ""

python run.py \
  --input data/test_leads.csv \
  --output data/output/test_results.csv \
  --workers 5

echo ""
echo "✅ Test complete! Results in: data/output/test_results.csv"
