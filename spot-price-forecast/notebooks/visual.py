spot_data = spot.load_spot_data('../data/spot_prices_fi_2016_2023.csv', date_col="date", price_col="elspot-fi")
plot_predictions(spot_data, slider=True)


model_kwargs = {
    "Time + Price Lags": {"daily_price_lags": [1,2,3,7], "time_features": True},
    "Time + Price Lags + External Features": {"daily_price_lags": [1,2,3,7], "time_features": True, "external_features": EXTERNAL_FEATURES},
    "Time + Price Lags + External Features + External Lags": {"daily_price_lags": [1,2,3,7], "time_features": True, "external_features": EXTERNAL_FEATURES, "daily_external_lags": [1,7]},
}

lm_predictions = {}
lm_coeffs = {}
for title, kwargs in model_kwargs.items():
    model = models.LinearModel(**kwargs)
    data = model.preprocess_data(spot_data)
    predictions, _, coeffs = trainer.year_on_year_training(data, model)
    lm_predictions[title] = predictions
    lm_coeffs[title] = coeffs


# Time coefficients for 2023
plot_time_coefficients(lm_coeffs["Time + Price Lags + External Features + External Lags"][2023], 
                       title="Coefficients for Time Features for 2023", save_dir="../images")

# Lagged price coefficients for 2023
plot_year_over_year_coefficients(lm_coeffs["Time + Price Lags + External Features + External Lags"], 
                                 keyword="y_lag", years=[2023], save_dir="../images")

# Custom metrics (top-k prediction accuracy) for all models
plot_custom_metrics(spot_data, lm_predictions, top_k=3, save_dir="../images")
