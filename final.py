import sys
import pandas as pd
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QFileDialog, QTableWidget, QTableWidgetItem,
                             QComboBox, QHBoxLayout, QLabel, QLineEdit,
                             QHeaderView, QMessageBox, QSizePolicy, QCheckBox) # Import QCheckBox
from PyQt5.QtCore import Qt
import numpy as np # Import numpy for isnan check

# Helper function to clean column names and table name
def clean_name(name):
    """
    Converts names to lowercase and replaces non-English characters.
    Also replaces spaces with underscores and removes invalid characters for SQL identifiers.
    """
    if not isinstance(name, str):
        name = str(name) # Ensure name is a string

    name = name.lower()
    # Simple replacement for common Turkish characters
    replacements = {
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
        'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U',
        ' ': '_' # Replace spaces with underscores
    }
    for original, replacement in replacements.items():
        name = name.replace(original, replacement)
    # Remove any characters that are not alphanumeric or underscore
    name = ''.join(e for e in name if e.isalnum() or e == '_')
    # Ensure it doesn't start with a number (MySQL identifiers can't start with a digit)
    if name and name[0].isdigit():
        name = '_' + name
    return name

class ExcelToSqlConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.dataframe = None
        self.column_widgets = {} # To store widgets for each column (data type, null, default, enum)
        # Removed cleaned_to_original_col_map, will store original name on the item itself

        self.initUI()

    def initUI(self):
        self.setWindowTitle('Excel/CSV to SQL Converter')
        self.setGeometry(100, 100, 1000, 700) # Increase window size

        layout = QVBoxLayout()

        # File selection
        file_layout = QHBoxLayout()
        self.file_label = QLabel('No file selected')
        file_layout.addWidget(self.file_label)
        self.select_file_button = QPushButton('Select File')
        self.select_file_button.clicked.connect(self.select_file)
        file_layout.addWidget(self.select_file_button)
        layout.addLayout(file_layout)

        # Table Name input
        table_name_layout = QHBoxLayout()
        table_name_layout.addWidget(QLabel('MySQL Table Name:'))
        self.table_name_input = QLineEdit('table') # Default table name
        table_name_layout.addWidget(self.table_name_input)
        layout.addLayout(table_name_layout)


        # Table to display columns and data types
        self.column_table = QTableWidget()
        # Increased column count for Allow Null and Default Value
        self.column_table.setColumnCount(5)
        self.column_table.setHorizontalHeaderLabels(['Column Name', 'MySQL Data Type', 'Allow NULL', 'Default Value', 'ENUM Values (comma-separated)'])
        # Adjust resize modes for better layout
        self.column_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch) # Column Name
        self.column_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents) # Data Type
        self.column_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # Allow NULL
        self.column_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch) # Default Value
        self.column_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch) # ENUM Values
        layout.addWidget(self.column_table)

        # Output filename input
        filename_layout = QHBoxLayout()
        filename_layout.addWidget(QLabel('Output SQL Filename:'))
        self.filename_input = QLineEdit('create-table.sql')
        filename_layout.addWidget(self.filename_input)
        layout.addLayout(filename_layout)

        # Generate SQL button
        self.generate_sql_button = QPushButton('Generate SQL File')
        self.generate_sql_button.clicked.connect(self.generate_sql)
        self.generate_sql_button.setEnabled(False) # Disable until file is selected
        layout.addWidget(self.generate_sql_button)

        self.setLayout(layout)

    def select_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Excel or CSV File", "",
                                                   "Excel Files (*.xls *.xlsx);;CSV Files (*.csv);;All Files (*)", options=options)

        if file_path:
            self.file_path = file_path
            self.file_label.setText(f'Selected: {self.file_path}')
            self.load_file()

    def load_file(self):
        try:
            if self.file_path.endswith('.csv'):
                # Try different encodings for CSV
                try:
                    self.dataframe = pd.read_csv(self.file_path)
                except UnicodeDecodeError:
                    try:
                        self.dataframe = pd.read_csv(self.file_path, encoding='latin1')
                    except UnicodeDecodeError:
                        self.dataframe = pd.read_csv(self.file_path, encoding='cp1252')
            else: # Assume Excel file (.xls or .xlsx)
                # pandas requires xlrd for .xls files and openpyxl for .xlsx files
                self.dataframe = pd.read_excel(self.file_path)

            self.display_columns()
            self.generate_sql_button.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not load file: {e}')
            self.dataframe = None
            self.column_table.setRowCount(0)
            self.generate_sql_button.setEnabled(False)
            self.file_label.setText('No file selected')
            self.file_path = None

    def display_columns(self):
        if self.dataframe is not None:
            columns = self.dataframe.columns.tolist()
            self.column_table.setRowCount(len(columns))
            self.column_widgets = {} # Reset stored widgets
            # self.cleaned_to_original_col_map = {} # Reset mapping - removed

            # Get the cleaned table name early to use in column renaming if needed
            cleaned_table_name = clean_name(self.table_name_input.text() if self.table_name_input.text() else 'table')

            # Keep track of cleaned names to ensure uniqueness during initial load
            initial_cleaned_names = {}

            for i, original_col in enumerate(columns):
                cleaned_col = clean_name(original_col)

                # Handle 'id' column conflict and ensure uniqueness
                if cleaned_col == 'id':
                     cleaned_col = f'id_{cleaned_table_name}'
                     # Ensure the new name is also clean and unique
                     temp_cleaned_col = cleaned_col
                     k = 1
                     while temp_cleaned_col in initial_cleaned_names:
                          temp_cleaned_col = f'{cleaned_col}_{k}'
                          k += 1
                     cleaned_col = temp_cleaned_col
                elif cleaned_col in initial_cleaned_names:
                     # Handle conflicts for other column names
                     temp_cleaned_col = cleaned_col
                     k = 1
                     while temp_cleaned_col in initial_cleaned_names:
                          temp_cleaned_col = f'{cleaned_col}_{k}'
                          k += 1
                     cleaned_col = temp_cleaned_col

                initial_cleaned_names[cleaned_col] = True # Mark this cleaned name as used

                # Store widgets using the initial cleaned name as the key
                self.column_widgets[cleaned_col] = {}

                # Column Name (Editable)
                item = QTableWidgetItem(cleaned_col)
                item.setFlags(item.flags() | Qt.ItemIsEditable) # Make column name editable
                # Store the original column name on the item itself
                item.original_col_name = original_col
                self.column_table.setItem(i, 0, item)


                # MySQL Data Type (ComboBox)
                data_type_combo = QComboBox()
                data_type_combo.addItems(['VARCHAR(255)', 'INT(11)', 'TEXT', 'LONGTEXT', 'DATE', 'TIME', 'DATETIME', 'ENUM', 'BIGINT']) # Added BIGINT
                suggested_type = self.suggest_data_type(original_col) # Suggest based on original data
                data_type_combo.setCurrentText(suggested_type)
                self.column_table.setCellWidget(i, 1, data_type_combo)
                self.column_widgets[cleaned_col]['data_type'] = data_type_combo


                # Allow NULL (CheckBox)
                allow_null_checkbox = QCheckBox()
                allow_null_checkbox.setChecked(True) # Default to allowing NULL
                # Center the checkbox
                checkbox_container = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_container)
                checkbox_layout.addWidget(allow_null_checkbox)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(0,0,0,0)
                self.column_table.setCellWidget(i, 2, checkbox_container)
                self.column_widgets[cleaned_col]['allow_null'] = allow_null_checkbox


                # Default Value (LineEdit)
                default_value_input = QLineEdit()
                default_value_input.setPlaceholderText("Optional default value")
                self.column_table.setCellWidget(i, 3, default_value_input)
                self.column_widgets[cleaned_col]['default_value'] = default_value_input


                # ENUM Values (Editable Cell)
                enum_item = QTableWidgetItem("")
                # QTableWidgetItem does not have setPlaceholderText, handle visually if needed
                # enum_item.setPlaceholderText("Comma-separated values if ENUM")
                enum_item.setFlags(enum_item.flags() | Qt.ItemIsEditable) # Make cell editable
                self.column_table.setItem(i, 4, enum_item)
                self.column_widgets[cleaned_col]['enum_values_item'] = enum_item # Store the item


    def suggest_data_type(self, col):
        """
        Basic data type suggestion based on column content.
        Improved handling for integer detection and date/time.
        """
        # Drop NaN values for type suggestion
        series = self.dataframe[col].dropna()

        if series.empty:
            return 'VARCHAR(255)' # Default for empty columns

        # Check if all non-null values can be represented as integers
        try:
            # Check if the series is numeric first
            if pd.api.types.is_numeric_dtype(series):
                 # Attempt conversion to int, coercing errors to NaN
                 int_series = pd.to_numeric(series, errors='coerce')
                 # Check if all non-NaN values in the original series are close to their integer conversion
                 # Also check if the conversion introduced new NaNs (meaning some values weren't integers)
                 if np.all(np.isclose(series.dropna().astype(float), int_series.dropna().astype(int))) and \
                    int_series.notna().sum() == series.notna().sum():

                      # Check range for INT(11)
                      if series.min() >= -2147483648 and series.max() <= 2147483647:
                           return 'INT(11)'
                      else:
                           return 'BIGINT' # Suggest BIGINT if outside INT(11) range
                 else:
                      return 'VARCHAR(255)' # Contains non-integer numeric values

        # Corrected indentation for the except block
        except Exception:
            pass # Conversion failed, proceed to other checks

        # Try to detect if it's a date/datetime
        try:
            # Attempt to convert to datetime, errors='coerce' will turn unparseable dates into NaT (Not a Time)
            # If a significant portion are successfully converted, suggest DATETIME
            datetime_series = pd.to_datetime(series, errors='coerce')
            valid_dates_count = datetime_series.notna().sum()
            if valid_dates_count / len(series) > 0.8: # If more than 80% are valid dates/datetimes
                # Further check if it contains time component
                # Use isnat to check for NaT values robustly
                # Check only non-NaT values for time component
                if any(dt.time() != pd.to_datetime('00:00:00').time() for dt in datetime_series.dropna()):
                     return 'DATETIME'
                else:
                     return 'DATE' # Only date part seems present
            else:
                 return 'VARCHAR(255)' # Default to VARCHAR if not clearly numeric or date
        except Exception:
             return 'VARCHAR(255)' # Default to VARCHAR if conversion fails or not date/datetime like

        # If none of the above, default to VARCHAR
        return 'VARCHAR(255)'


    def generate_sql(self):
        if self.dataframe is None or not self.column_widgets:
            QMessageBox.warning(self, 'Warning', 'No data loaded or column types not selected.')
            return

        output_filename = self.filename_input.text()
        if not output_filename:
            QMessageBox.warning(self, 'Warning', 'Please enter an output filename.')
            return

        if not output_filename.lower().endswith('.sql'):
            output_filename += '.sql'

        table_name = self.table_name_input.text()
        if not table_name:
             QMessageBox.warning(self, 'Warning', 'Please enter a MySQL table name.')
             return

        cleaned_table_name = clean_name(table_name)
        if not cleaned_table_name:
             QMessageBox.warning(self, 'Warning', 'Invalid MySQL table name.')
             return

        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                # Generate CREATE TABLE statement
                f.write(f"CREATE TABLE `{cleaned_table_name}` (\n")
                column_defs = []

                # Add the auto-increment primary key 'id' column first
                column_defs.append("    `id` INT(11) AUTO_INCREMENT PRIMARY KEY")

                # Iterate through the rows in the table widget to get user-defined column details
                insert_column_names = [] # To store column names for the INSERT statement
                # Use a list to maintain order and handle potential user reordering
                ui_column_data = []
                for i in range(self.column_table.rowCount()):
                     col_name_item = self.column_table.item(i, 0)
                     if col_name_item is None or not col_name_item.text():
                          QMessageBox.warning(self, 'Warning', f"Row {i+1} has no column name. Skipping.")
                          continue

                     col_name = col_name_item.text() # The potentially edited name
                     original_col_name = getattr(col_name_item, 'original_col_name', None) # Get original name from item attribute

                     if original_col_name is None:
                          QMessageBox.warning(self, 'Warning', f"Could not retrieve original column name for row {i+1} ('{col_name}'). Skipping.")
                          continue

                     # Get widgets for this row
                     data_type_combo = self.column_table.cellWidget(i, 1)
                     allow_null_checkbox_container = self.column_table.cellWidget(i, 2)
                     default_value_input = self.column_table.cellWidget(i, 3)
                     enum_values_item = self.column_table.item(i, 4)

                     if isinstance(data_type_combo, QComboBox) and \
                        isinstance(allow_null_checkbox_container, QWidget) and \
                        isinstance(default_value_input, QLineEdit) and \
                        enum_values_item is not None:

                          allow_null_checkbox = allow_null_checkbox_container.findChild(QCheckBox)

                          if allow_null_checkbox:
                               data_type = data_type_combo.currentText()
                               allow_null = allow_null_checkbox.isChecked()
                               default_value = default_value_input.text().strip()
                               enum_values_text = enum_values_item.text().strip()

                               ui_column_data.append({
                                   'current_name': col_name,
                                   'original_name': original_col_name,
                                   'data_type': data_type,
                                   'allow_null': allow_null,
                                   'default_value': default_value,
                                   'enum_values_text': enum_values_text
                               })
                          else:
                               QMessageBox.warning(self, 'Warning', f"Could not retrieve checkbox for column '{col_name}'. Skipping definition.")
                     else:
                          QMessageBox.warning(self, 'Warning', f"Could not retrieve all widgets for column '{col_name}'. Skipping definition.")

                # Now generate CREATE TABLE definitions based on collected UI data
                for col_data in ui_column_data:
                    col_name = col_data['current_name']
                    data_type = col_data['data_type']
                    allow_null = col_data['allow_null']
                    default_value = col_data['default_value']
                    enum_values_text = col_data['enum_values_text']

                    definition = f"    `{col_name}` {data_type}"

                    if data_type == 'ENUM':
                         enum_values = []
                         for val in enum_values_text.split(','):
                              cleaned_val = val.strip()
                              if cleaned_val:
                                   escaped_val = cleaned_val.replace("'", "''")
                                   quoted_val = f"'{escaped_val}'"
                                   enum_values.append(quoted_val)
                         if enum_values:
                              definition += f"({', '.join(enum_values)})"
                         else:
                              definition += "('')" # Empty ENUM if no valid values entered

                    # Add NULL/NOT NULL constraint
                    if not allow_null:
                         definition += " NOT NULL"
                    else:
                         definition += " NULL" # Explicitly add NULL

                    # Add DEFAULT value
                    if default_value:
                         # Need to format default value based on data type
                         if data_type.startswith('VARCHAR') or data_type in ['TEXT', 'LONGTEXT', 'ENUM', 'DATE', 'TIME', 'DATETIME']:
                              # Corrected escaping for default string/date/time values
                              escaped_default = default_value.replace("'", "''")
                              definition += f" DEFAULT '{escaped_default}'"
                         elif data_type.startswith('INT') or data_type == 'BIGINT':
                              # Ensure integer default value is valid
                              try:
                                   int(default_value)
                                   definition += f" DEFAULT {default_value}"
                              except ValueError:
                                   QMessageBox.warning(self, 'Warning', f"Invalid default value '{default_value}' for INT/BIGINT column '{col_name}'. Skipping default.")
                         else:
                               # For other types, default to quoting as string with escaping
                               escaped_default = default_value.replace("'", "''")
                               definition += f" DEFAULT '{escaped_default}'"

                    # Add COLLATE for string types
                    if data_type.startswith('VARCHAR') or data_type in ['TEXT', 'LONGTEXT', 'ENUM']:
                         definition += " COLLATE 'utf8_general_ci'"


                    column_defs.append(definition)
                    insert_column_names.append(col_name) # Add to insert list (excluding the auto 'id')


                f.write(",\n".join(column_defs))
                f.write("\n);\n\n")

                # Generate INSERT INTO statements
                # Write INSERT INTO header once before the loop, using column names from the table widget
                f.write(f"INSERT INTO `{cleaned_table_name}` ({', '.join([f'`{c}`' for c in insert_column_names])}) VALUES\n")

                values_list = []
                for index, row in self.dataframe.iterrows():
                    row_values = []
                    # Iterate through the column names we plan to insert (from the table widget, excluding 'id')
                    for col_data in ui_column_data:
                         col_name = col_data['current_name'] # Potentially edited name
                         original_col_name = col_data['original_name'] # Original dataframe name
                         data_type = col_data['data_type'] # Selected data type

                         # Use the original_col_name to get the value from the dataframe
                         value = row[original_col_name]

                         # Handle NaN values (missing data) - convert to NULL in SQL
                         if pd.isna(value): # Use pd.isna for robust check
                             row_values.append('NULL')
                         else:
                            # Basic type handling for SQL values based on selected data type
                            if data_type.startswith('VARCHAR') or data_type in ['TEXT', 'LONGTEXT', 'ENUM']:
                                # Escape single quotes in strings and wrap in quotes
                                escaped_value = str(value).replace("'", "''")
                                quoted_value = f"'{escaped_value}'"
                                row_values.append(quoted_value)
                            elif data_type.startswith('INT') or data_type == 'BIGINT': # Handle BIGINT as well
                                try:
                                     # Ensure integer values are formatted correctly
                                    # Convert to int, then string
                                    row_values.append(str(int(value)))
                                except (ValueError, TypeError): # Catch both ValueError and TypeError
                                     row_values.append('NULL') # If not a valid integer, treat as NULL
                            elif data_type in ['DATE', 'TIME', 'DATETIME']:
                                # Attempt to format date/datetime values
                                try:
                                    # pandas to_datetime is flexible
                                    dt_object = pd.to_datetime(value)
                                    if data_type == 'DATE':
                                        row_values.append(f"'{dt_object.strftime('%Y-%m-%d')}'")
                                    elif data_type == 'TIME':
                                         row_values.append(f"'{dt_object.strftime('%H:%M:%S')}'")
                                    elif data_type == 'DATETIME':
                                         row_values.append(f"'{dt_object.strftime('%Y-%m-%d %H:%M:%S')}'")
                                except Exception:
                                    row_values.append('NULL') # If date/time conversion fails, treat as NULL
                            else:
                                # Default to string representation for other types, escaping and quoting
                                escaped_value = str(value).replace("'", "''")
                                quoted_value = f"'{escaped_value}'"
                                row_values.append(quoted_value)


                    values_list.append(f"({', '.join(row_values)})")

                # Write INSERT statements in batches for potentially large files
                batch_size = 1000 # Define batch size
                for i in range(0, len(values_list), batch_size):
                    batch = values_list[i:i + batch_size]
                    # For the first batch, just write the values. For subsequent batches,
                    # write a comma before the values to continue the INSERT statement.
                    if i > 0:
                         f.write(",\n") # Continue the previous INSERT statement with a comma

                    f.write(",\n".join(batch))

                # Close the entire INSERT statement after the loop
                f.write(";\n")


            QMessageBox.information(self, 'Success', f'SQL file "{output_filename}" generated successfully.')

        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not generate SQL file: {e}')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ExcelToSqlConverter()
    ex.show()
    sys.exit(app.exec_())
