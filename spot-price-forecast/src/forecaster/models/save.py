import pickle
import json
import os
from datetime import datetime

def save_model(model, filepath, metadata=None):
    """
    Save a trained model to disk.
    
    Args:
        model: The trained LinearModel instance
        filepath: Path where to save the model (e.g., 'models/my_model.pkl')
        metadata: Optional dict with additional info (training date, metrics, etc.)
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    
    # Prepare model data
    model_data = {
        'coeffs': model.coeffs,
        'daily_price_lags': model.daily_price_lags,
        'time_features': model.time_features,
        'external_features': model.external_features,
        'daily_external_lags': model.daily_external_lags,
        'nFeatures': model.nFeatures,
        'fit_coeffs': model.fit_coeffs,
        'saved_at': datetime.now().isoformat(),
        'metadata': metadata or {}
    }
    
    # Save with pickle
    with open(filepath, 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"Model saved to: {filepath}")
    
    # Also save a human-readable JSON version (without coeffs for readability)
    json_filepath = filepath.replace('.pkl', '_info.json')
    info_data = {k: v for k, v in model_data.items() if k != 'coeffs'}
    info_data['num_coefficients'] = len(model.coeffs)
    
    with open(json_filepath, 'w') as f:
        json.dump(info_data, f, indent=2)
    
    print(f"Model info saved to: {json_filepath}")


def load_model(filepath):
    """
    Load a trained model from disk.
    
    Args:
        filepath: Path to the saved model file
        
    Returns:
        model: The loaded LinearModel instance, ready to use
    """
    from forecaster.models import models
    
    # Load the model data
    with open(filepath, 'rb') as f:
        model_data = pickle.load(f)
    
    # Recreate the model
    model = models.LinearModel(
        daily_price_lags=model_data['daily_price_lags'],
        time_features=model_data['time_features'],
        external_features=model_data['external_features'],
        daily_external_lags=model_data['daily_external_lags'],
        fit_coeffs=model_data['fit_coeffs']
    )
    
    # Restore the trained coefficients
    model.coeffs = model_data['coeffs']
    
    print(f"Model loaded from: {filepath}")
    print(f"Model was saved at: {model_data.get('saved_at', 'Unknown')}")
    
    if model_data.get('metadata'):
        print("Metadata:", model_data['metadata'])
    
    return model


# Example usage functions
def save_model_with_metrics(model, metrics, train_data, test_data, filepath):
    """
    Convenience function to save model with training metrics.
    """
    metadata = {
        'train_mae': metrics['train']['mean_absolute_error'],
        'train_rmse': metrics['train']['root_mean_squared_error'],
        'test_mae': metrics['test']['mean_absolute_error'],
        'test_rmse': metrics['test']['root_mean_squared_error'],
        'train_samples': len(train_data),
        'test_samples': len(test_data),
        'train_date_range': f"{train_data.index.min()} to {train_data.index.max()}",
        'test_date_range': f"{test_data.index.min()} to {test_data.index.max()}"
    }
    
    save_model(model, filepath, metadata)