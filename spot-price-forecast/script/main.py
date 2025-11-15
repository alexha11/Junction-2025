import pandas as pd

# Load CSV
df = pd.read_csv("dummy.csv")

# Select only timestamp and PricePredict_cpkWh columns
df_filtered = df[["timestamp", "Price_cpkWh"]]

# Save to a new CSV (optional)
df_filtered.to_csv("filtered_file.csv", index=False)

# Print result
print(df_filtered.head())
