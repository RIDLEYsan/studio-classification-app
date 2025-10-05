#!/bin/bash
cd /home/site/wwwroot
python -m streamlit run streamlit_classifier_sqlite.py --server.port 8000 --server.address 0.0.0.0
