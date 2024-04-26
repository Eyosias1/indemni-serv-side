import os
from datetime import datetime, time
import markdown2
import pdfkit
import pandas as pd
from flask_cors import CORS
import tempfile
import re
import csv
from werkzeug.datastructures import FileStorage
from flask import Flask, request, send_file
# Define the function

app = Flask(__name__)
CORS(app)
def from_shift_to_dict1(file_storage):
    shifts_dict = {}
    # Reset the file pointer to the start of the file
    file_storage.seek(0)
    # Read all lines or iterate directly
    lines = file_storage.readlines()  # Read all lines at once
    lines_iterator = iter(lines)  # Convert the list of lines into an iterator

    # Skip the header by calling next on the iterator
    next(lines_iterator)

    # Now process each line in the file
    for line_bytes in lines_iterator:
        line = line_bytes.decode('utf-8').strip()  # Decode line if FileStorage reads as bytes
        parts = line.split('|')
        if len(parts) == 3:
            date, start_time, end_time = parts
            try:
                formatted_date = datetime.strptime(date.strip(), "%Y-%m-%d").strftime("%d-%m-%Y")
                if formatted_date not in shifts_dict:
                    shifts_dict[formatted_date] = [(start_time.strip(), end_time.strip())]
                else:
                    shifts_dict[formatted_date].append((start_time.strip(), end_time.strip()))
            except ValueError:
                # This try-except block is to handle incorrect date formats or skip malformed lines
                continue

    return shifts_dict


def from_shifts_df_to_dict(df_final_sorted):
    shifts_dict = {}
    # Iterate over the DataFrame rows
    for index, row in df_final_sorted.iterrows():
        date, start_time, end_time = row['date'], row['start time'], row['end time']

        # Format the date
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        # Append the start and end times to the shifts_dict
        if formatted_date not in shifts_dict:
            shifts_dict[formatted_date] = [(start_time, end_time)]
        else:
            shifts_dict[formatted_date].append((start_time, end_time))
    return shifts_dict

def rename_columns_with_regex(df):
    # Using regular expressions to find and rename columns
    df.columns = [re.sub(r'start[\w-]*datetime', 'start_datetime', col, flags=re.I) for col in df.columns]
    df.columns = [re.sub(r'end[\w-]*datetime', 'end_datetime', col, flags=re.I) for col in df.columns]
    return df

def detect_separator(file_storage):
    # Open the file in text mode and read a small part to guess the delimiter
    content = file_storage.stream.read(4096)
    # Move the pointer back to the start of the file for further processing
    file_storage.stream.seek(0)
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(content.decode('iso-8859-1'))
        return dialect.delimiter
    except csv.Error:
        # Fallback strategy: try common delimiters if sniffer fails
        common_delimiters = [',', ';', '\t', '|']
        for delimiter in common_delimiters:
            if delimiter in content.decode('iso-8859-1'):
                return delimiter
        raise Exception("Could not determine the delimiter")

def decide_dayfirst(df, date_column):
    day_first = True
    # Sample up to 10 non-null date entries
    sample_dates = df[date_column].dropna().head(10)
    for date_str in sample_dates:
        # Split the datetime string to isolate the date part
        date_part = date_str.split(' ')[0]  # Assumes date and time are separated by a space
        # Detect the separator and split by it
        if '-' in date_part:
            parts = date_part.split('-')
        elif '/' in date_part:
            parts = date_part.split('/')
        else:
            continue  # Skip if no recognizable separator is found
        # Try converting the first part of the date to an integer
        try:
            first_part = int(parts[0])
            if first_part > 32:
                day_first = False
                break  # If any date in the sample indicates day first, we assume day first for all
        except ValueError:
            continue  # Skip if conversion fails

    return day_first
def process_dates(df, date_columns):
    for date_col in date_columns:
        day_first = decide_dayfirst(df, date_col)
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=day_first)

    # Format the dates and times as needed
    df['date'] = df['start_datetime'].dt.strftime('%Y-%m-%d')
    df['start time'] = df['start_datetime'].dt.strftime('%H:%M:%S')
    df['end time'] = df['end_datetime'].dt.strftime('%H:%M:%S')
    return df
def extract_from_shift(file_storage):
    # Initialize an empty list to hold the shift data
    if file_storage.filename.endswith('.csv'):
        delimiter = detect_separator(file_storage)
        # if the file is comma separated and contains western european characters
        df = pd.read_csv(file_storage, encoding='iso-8859-1', sep=delimiter)
        df = rename_columns_with_regex(df)
        date_columns = ['start_datetime', 'end_datetime']  # Specify the date columns
        df = process_dates(df, date_columns)

        # Select only the new columns in the desired order
        df_final = df[['date', 'start time', 'end time']]

        # Sort the dataframe by 'date' and 'start time'
        df_final_sorted = df_final.sort_values(by=['date', 'start time'])

        # Save the sorted dataframe to a new CSV file
        shifts_dict = from_shifts_df_to_dict(df_final_sorted)
    elif file_storage.filename.endswith('.txt'):
        shifts_dict = from_shift_to_dict1(file_storage)
    return shifts_dict


def calculer_indemnite_dimanche(shifts):
    dimanche_less_3 = 12.26
    dimanche_more_3 = 28.51
    sunday_indemnities = {}  # Dictionnaire pour les indemnités de dimanche

    for date, shift_times in shifts.items():
        shift_date = datetime.strptime(date, "%d-%m-%Y")
        is_sunday = shift_date.weekday() == 6  # Sunday is 6

        if is_sunday:
            indemnites_shifts = {}  # Liste pour stocker les indemnités de chaque shift de dimanche
            for start, end in shift_times:
                shift_id = f"{date}_{start}_{end}"
                start_time = datetime.strptime(start, "%H:%M:%S")
                end_time = datetime.strptime(end, "%H:%M:%S")
                duration = (end_time - start_time).total_seconds() / 3600
                indemnites_shifts[shift_id]= dimanche_more_3 if duration >= 3 else dimanche_less_3

            max_indemnity_value = max(indemnites_shifts.values())
            # Sélectionner l'indemnité la plus élevée pour la date et la stocker dans le dictionnaire

             # Attribuer l'indemnité la plus élevée au premier shift qui la rencontre, zéro aux autres
            max_assigned = False
            for shift_id in indemnites_shifts:
                if indemnites_shifts[shift_id] == max_indemnity_value and not max_assigned:
                    sunday_indemnities[shift_id] = max_indemnity_value
                    max_assigned = True  # S'assurer que l'indemnité maximale est attribuée une seule fois
                else:
                    sunday_indemnities[shift_id] = 0  # Les autres shifts reçoivent zéro


    return sunday_indemnities


def generate_markdown2(shifts, meal_voucher_value, night_hour_value):
    # Define your specific times as datetime.time objects for comparison
    time_14_15 = time(14, 15)
    time_11_45 = time(11, 45)
    time_21_15 = time(21, 15)
    time_18_45 = time(18, 45)

    month_translation = {
    'January': 'Janvier', 'February': 'Février', 'March': 'Mars', 'April': 'Avril',
    'May': 'Mai', 'June': 'Juin', 'July': 'Juillet', 'August': 'Août',
    'September': 'Septembre', 'October': 'Octobre', 'November': 'Novembre', 'December': 'Décembre'
    }

    shifts_key = list(shifts.keys())
    date_Obj = datetime.strptime(shifts_key[0], "%d-%m-%Y")
    month_text = date_Obj.strftime("%B")
    month_text = month_translation[month_text]
    year_text = date_Obj.strftime("%Y")
    markdown = f"# {month_text} {year_text} Rapport\n\n"
    markdown += "Date | Shifts | Panier repas | Heures nuit maj. | IND DIMANCHE \n| --- | --- | :---: | :---: | :---:\n"
    total_meal_vouchers = 0
    total_night_hours = 0
    total_dimanche_ind = 0
    dimanche_ind = 0
    total_shift_month = 0
    sunday_indemnities = calculer_indemnite_dimanche(shifts)

    for date, shift_times in shifts.items():
        for start, end in shift_times:
            shift_id = f"{date}_{start}_{end}"
            start_time = datetime.strptime(start, "%H:%M:%S")
            end_time = datetime.strptime(end, "%H:%M:%S")
            meal_voucher = "✓" if ((start_time.time() <= time_11_45  and
                                    end_time.time() >= time_14_15)   or
                                    (start_time.time() <= time_18_45 and
                                     end_time.time() >= time_21_15)) else ""

            night_hours = round(max((end_time - datetime.strptime("21:00:00", "%H:%M:%S")).total_seconds() / 3600, 0), 2)
            shift_date = datetime.strptime(date, "%d-%m-%Y")
            is_sunday = shift_date.weekday() == 6  # Sunday is 6
            dimanche_ind = sunday_indemnities[shift_id] if is_sunday else 0
            markdown += f"{date} | {start} - {end} | {meal_voucher} | {night_hours if night_hours else ''} | <span class='number'>{'{:.2f}'.format(dimanche_ind)}</span>\n"
            total_meal_vouchers += 1 if meal_voucher else 0
            total_night_hours += night_hours
            total_dimanche_ind += dimanche_ind if is_sunday else 0
            total_shift_month += 1

    # Calculating the totals
    total_meal_voucher_amount = total_meal_vouchers * meal_voucher_value
    total_night_hour_amount = total_night_hours * night_hour_value
    total_amount = total_meal_voucher_amount + total_night_hour_amount + total_dimanche_ind

    # Adding the total to the markdown
    markdown += f"**Total** | **{total_shift_month} shift** | **{total_meal_vouchers} paniers repas** | **{total_night_hours:.3f}h** | <span class='number'>**{total_dimanche_ind:.3f}**</span> €\n"
    markdown += "\n## Calcul des indemnités et suppléments\n"
    markdown += f"- **Indemnités de repas** : {total_meal_vouchers} paniers repas à {meal_voucher_value:.3f} € chacun = {total_meal_voucher_amount:.2f} €\n"
    markdown += f"- **Heures de nuit** : {total_night_hours:.2f} heures à un supplément de {night_hour_value:.3f} € par heure = {total_night_hour_amount:.2f} €\n"
    markdown += f"- **Indémnités de travail de dimanche** : {total_dimanche_ind:.3f} €\n\n"
    markdown += f"**Total général** : <span class='number'>**{total_amount:.2f}</span> €**\n"

    return markdown, total_amount, [month_text, year_text]

def parse_to_gen_mark_pdf(annual_markdown_report, meal_voucher_amount, night_hour_supplement, css_style, full_name, shifts_dict):
    current_month = None
    markdown_yearly_report = "\n\n\n# RAPPORT ANNUEL \n| Mois | Revenue (€) |\n|---|:---:|\n"
    month_shifts = {}
    total_cash = 0
    total = 0
    for date, shift_times in sorted(shifts_dict.items(), key=lambda x: datetime.strptime(x[0], "%d-%m-%Y")):
            date_obj = datetime.strptime(date, "%d-%m-%Y")
            if current_month is None or date_obj.month == current_month:
                month_shifts[date] = shift_times
                current_month = date_obj.month
            else:
                markdown_report, total_cash, name = generate_markdown2(month_shifts, meal_voucher_amount, night_hour_supplement)
                # Append this month's report and summary to the annual data
                annual_markdown_report += markdown_report + "\n\n"  # Add a couple of newlines between months
                markdown_yearly_report += f"{name[0]} {name[1]} | <span class='number'>**{total_cash:.3f}**</span> € |\n"
                total += total_cash
                current_month = date_obj.month
                month_shifts = {date: shift_times}
    # process the last month
    if month_shifts:
        markdown_report, total_cash, name = generate_markdown2(month_shifts, meal_voucher_amount, night_hour_supplement)
        annual_markdown_report += markdown_report + "\n\n"  # Add a couple of newlines between months
        markdown_yearly_report += f"{name[0]} {name[1]} | <span class='number'>**{total_cash:.3f}**</span> € |\n"
        total += total_cash
    # write the annaual report
    markdown_yearly_report += f"**TOTAL** |  <span class='number'>**{total:.3f}**</span> € |\n"
    markdown_yearly_report += f"\n**Somme Total** Panier repas,  Heure supplémentaire non Majoré et Indémnités de travail de dimanche = <span class='number'>**{total:.3f}** €</span>\n"

    # In one pdf
    annual_markdown_report += markdown_yearly_report + "\n\n"  # Add a couple of newlines between months
    markdown_text = annual_markdown_report
    html_text = css_style + markdown2.markdown(markdown_text, extras=["tables"]) + '</body></html>'
    annual_pdf_output_path = os.path.join(f"{full_name}_Annual_Report.pdf")
    #
    print(f"Annual PDF report generated: {annual_pdf_output_path}")

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf_file:
        temp_pdf_file.write(pdfkit.from_string(html_text, options={'encoding': 'UTF-8'}))
        temp_pdf_file_path = temp_pdf_file.name

    return temp_pdf_file_path

css_style = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
    table {
        width: 100%;
        border-collapse: collapse;
    }
    th, td {
        border: 1px solid black;
        padding: 8px;
        text-align: left;
    }
    th {
        background-color: #e6f7ff;
        font-size: 16px;
    }
    .number {
    color: green;
    font-weight: bold;
    }
    </style>
</head>
<body>
    """

@app.route('/process-csv', methods=['POST'])
def process_csv():
    uploaded_file_txt = request.files.get('txtfile')
    uploaded_file_csv = request.files.get('csvfile')
    if uploaded_file_csv:
        shift_dict_1 = extract_from_shift(uploaded_file_csv)
    else:
        shift_dict_1 = extract_from_shift(uploaded_file_txt)

    full_name = request.form['fullname']
    hourly_rate_input = request.form['hourlyrate']
    meal_ind = request.form['PanRepas']
    meal_voucher_amount = 13.78 if meal_ind == "" else float(meal_ind)
    taux_horaire_net = 11.07 if hourly_rate_input == "" else float(hourly_rate_input)
    increased_hourly_rate = taux_horaire_net * (20 / 100)
    night_hour_supplement = increased_hourly_rate
    annual_markdown_report = f"# Nom : {full_name}\n"
    pdf_to_file_path = parse_to_gen_mark_pdf(annual_markdown_report, meal_voucher_amount, night_hour_supplement, css_style, full_name, shift_dict_1)
    # Return the PDF as a file attachment
    return send_file(
        pdf_to_file_path,
        mimetype='application/pdf',
        as_attachment=True,
    )

if __name__ == '__main__':
    app.run(debug=True)