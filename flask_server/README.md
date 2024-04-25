# Shift Processing and PDF Report Generation Server

## Overview

This Flask server is designed for processing shift data and generating PDF reports that summarize meal vouchers and extra hours compensation. It handles file uploads in both CSV and TXT formats, processes data to calculate compensations, and generates detailed PDF reports showcasing all the meal vouchers and extra hours based on the shift data.

## Features

- **File Uploads**: Accepts CSV or TXT files containing detailed shift data.
- **Automatic Delimiter Detection**: Identifies CSV delimiters to correctly parse files.
- **Column Renaming**: Uses regular expressions to standardize column names based on patterns.
- **Date Format Auto-Detection**: Dynamically adjusts parsing strategies for date columns based on content.
- **Compensation Calculation**: Calculates meal vouchers and extra pay for night and Sunday shifts.
- **PDF Reporting**: Converts data and calculations into a styled PDF report for easy distribution and printing.

## Installation

Ensure you have Python installed on your machine, and then install the required dependencies:

### Requirements

The server depends on several third-party libraries, which can be installed via pip:

```bash
pip install Flask gunicorn markdown2 pdfkit pandas flask_cors
```

Alternatively, you can use the requirements.txt file:

```bash
gunicorn
Flask
markdown2
pdfkit
pandas
flask_cors
```

Install using:

```bash
pip install -r requirements.txt
```