# New Supplier Testing and Ranking Code
import pandas as pd
import numpy as np
import joblib
import random

# Load the trained model
def load_trained_model(model_path='supplier_ranking_model.pkl'):
    """Load the saved model"""
    try:
        model_data = joblib.load(model_path)
        return model_data['model'], model_data['feature_names']
    except FileNotFoundError:
        print("Error: Model file not found! Please ensure 'supplier_ranking_model.pkl' exists.")
        return None, None

# Feature engineering function (same as training)
def prepare_features(df):
    """Create features for the model (same as training)"""
    df_features = df.copy()
    
    # Base engineered features
    feature_cols = [
        'lead_time_days', 'on_time_delivery_rate', 'defect_rate', 
        'past_performance_score', 'efficiency_score', 'quality_ratio', 'delivery_score'
    ]
    
    # Additional features
    df_features['performance_efficiency'] = (df_features['past_performance_score'] * 
                                           df_features['on_time_delivery_rate']) / (df_features['lead_time_days'] / 30)
    
    df_features['total_quality'] = (1 - df_features['defect_rate']) * df_features['past_performance_score']
    df_features['delivery_reliability'] = df_features['on_time_delivery_rate'] * (50 / df_features['lead_time_days'])
    
    df_features['risk_score'] = (df_features['defect_rate'] * 0.4 + 
                               (1 - df_features['on_time_delivery_rate']) * 0.3 + 
                               (df_features['lead_time_days'] / 90) * 0.3)
    
    df_features['composite_score'] = (
        df_features['on_time_delivery_rate'] * 0.25 +
        (1 - df_features['defect_rate']) * 0.25 +
        (df_features['past_performance_score'] / 5) * 0.25 +
        (50 / df_features['lead_time_days']) * 0.25
    )
    
    # Update feature list
    feature_cols.extend([
        'performance_efficiency', 'total_quality', 'delivery_reliability',
        'risk_score', 'composite_score'
    ])
    
    return df_features[feature_cols], feature_cols

# Generate test data for new suppliers
def generate_new_suppliers():
    """Generate 10 new suppliers with realistic data and company names"""
    
    # Company names
    company_names = [
        "Bosch", "Denso", "Magna", "Continental", "ZF Friedrichshafen",
        "Aisin Seiki", "Hyundai Mobis", "Valeo", "Faurecia", "Lear"
    ]
    
    # Set seed for reproducible results
    np.random.seed(123)
    random.seed(123)
    
    suppliers = []
    
    for i, company in enumerate(company_names):
        # Generate realistic supplier data with some variation
        
        # Create different performance profiles for variety
        if i < 3:  # First 3 companies - Excellent suppliers
            lead_time = np.random.uniform(8, 18)
            on_time_rate = np.random.uniform(0.92, 0.99)
            defect_rate = np.random.uniform(0.002, 0.015)
            past_score = np.random.uniform(4.3, 5.0)
        elif i < 6:  # Next 3 - Good suppliers
            lead_time = np.random.uniform(15, 35)
            on_time_rate = np.random.uniform(0.82, 0.92)
            defect_rate = np.random.uniform(0.015, 0.040)
            past_score = np.random.uniform(3.5, 4.3)
        elif i < 8:  # Next 2 - Average suppliers
            lead_time = np.random.uniform(25, 45)
            on_time_rate = np.random.uniform(0.65, 0.82)
            defect_rate = np.random.uniform(0.040, 0.090)
            past_score = np.random.uniform(2.8, 3.5)
        else:  # Last 2 - Below average suppliers
            lead_time = np.random.uniform(40, 70)
            on_time_rate = np.random.uniform(0.45, 0.65)
            defect_rate = np.random.uniform(0.090, 0.180)
            past_score = np.random.uniform(2.0, 2.8)
        
        # Calculate base engineered features
        efficiency_score = (on_time_rate * (1 - defect_rate)) / (lead_time / 30)
        quality_ratio = (1 - defect_rate) * past_score / 5
        delivery_score = on_time_rate * (60 / lead_time)
        
        supplier = {
            'supplier_name': company,
            'supplier_id': f'NEW_{i+1:03d}',
            'lead_time_days': lead_time,
            'on_time_delivery_rate': on_time_rate,
            'defect_rate': defect_rate,
            'past_performance_score': past_score,
            'efficiency_score': efficiency_score,
            'quality_ratio': quality_ratio,
            'delivery_score': delivery_score
        }
        
        suppliers.append(supplier)
    
    return pd.DataFrame(suppliers)

# Rank new suppliers using trained model
def rank_new_suppliers(model, feature_names, new_suppliers_df):
    """Rank new suppliers and add predictions"""
    
    # Prepare features
    X, _ = prepare_features(new_suppliers_df)
    
    # Get predictions and probabilities
    probs = model.predict(X)
    predictions = np.argmax(probs, axis=1) + 1  # Convert to 1-5 scale
    confidence = np.max(probs, axis=1)
    
    # Add predictions to dataframe
    result_df = new_suppliers_df.copy()
    result_df['predicted_relevance'] = predictions
    result_df['confidence'] = confidence
    
    # Add probability scores for each level
    for i in range(5):
        result_df[f'prob_level_{i+1}'] = probs[:, i]
    
    # Calculate ranking score
    result_df['ranking_score'] = result_df['predicted_relevance'] * result_df['confidence']
    
    # Sort by predicted relevance (descending) and confidence
    result_df = result_df.sort_values(
        ['predicted_relevance', 'confidence'], 
        ascending=[False, False]
    ).reset_index(drop=True)
    
    # Add rank
    result_df['rank'] = range(1, len(result_df) + 1)
    
    return result_df

# Performance summary
def generate_performance_summary(ranked_df):
    """Generate performance summary"""
    
    print("=== NEW SUPPLIER RANKING SUMMARY ===")
    print(f"Total suppliers evaluated: {len(ranked_df)}")
    
    # Count by relevance level
    relevance_counts = ranked_df['predicted_relevance'].value_counts().sort_index()
    print("\nSuppliers by Relevance Level:")
    for level in range(1, 6):
        count = relevance_counts.get(level, 0)
        print(f"  Level {level}: {count} suppliers")
    
    # Top 5 suppliers
    print("\n=== TOP 5 RECOMMENDED SUPPLIERS ===")
    top_5 = ranked_df.head(5)[['rank', 'supplier_name', 'predicted_relevance', 'confidence', 
                               'lead_time_days', 'on_time_delivery_rate', 'defect_rate', 'past_performance_score']]
    print(top_5.to_string(index=False))
    
    # Bottom 3 suppliers (if any poor performers)
    if len(ranked_df) >= 3:
        print(f"\n=== BOTTOM 3 SUPPLIERS (AVOID) ===")
        bottom_3 = ranked_df.tail(3)[['rank', 'supplier_name', 'predicted_relevance', 'confidence',
                                     'lead_time_days', 'on_time_delivery_rate', 'defect_rate', 'past_performance_score']]
        print(bottom_3.to_string(index=False))

def main():
    """Main function to test and rank new suppliers"""
    
    print("=== NEW SUPPLIER EVALUATION SYSTEM ===")
    print("Loading trained model...")
    
    # Load model
    model, feature_names = load_trained_model()
    if model is None:
        return
    
    print("Model loaded successfully!")
    
    # Generate new supplier data
    print("\nGenerating new supplier data...")
    new_suppliers = generate_new_suppliers()
    
    print(f"Generated data for {len(new_suppliers)} suppliers:")
    for i, name in enumerate(new_suppliers['supplier_name']):
        print(f"  {i+1}. {name}")
    
    # Rank suppliers
    print("\nEvaluating suppliers with AI model...")
    ranked_suppliers = rank_new_suppliers(model, feature_names, new_suppliers)
    
    # Display results
    generate_performance_summary(ranked_suppliers)
    
    # Save to CSV
    output_filename = 'new_supplier_rankings.csv'
    
    # Select columns for CSV output
    csv_columns = [
        'rank', 'supplier_name', 'supplier_id', 'predicted_relevance', 'confidence',
        'lead_time_days', 'on_time_delivery_rate', 'defect_rate', 'past_performance_score',
        'efficiency_score', 'quality_ratio', 'delivery_score', 'ranking_score'
    ]
    
    ranked_suppliers[csv_columns].to_csv(output_filename, index=False)
    print(f"\n✅ Results saved to '{output_filename}'")
    
    # Display full ranking table
    print(f"\n=== COMPLETE SUPPLIER RANKINGS ===")
    display_columns = ['rank', 'supplier_name', 'predicted_relevance', 'confidence',
                      'lead_time_days', 'on_time_delivery_rate', 'defect_rate', 'past_performance_score']
    print(ranked_suppliers[display_columns].round(4).to_string(index=False))
    
    return ranked_suppliers

# Additional utility function to test individual supplier
def evaluate_single_supplier(model, supplier_name, lead_time, on_time_rate, defect_rate, past_score):
    """Evaluate a single supplier quickly"""
    
    # Create supplier dataframe
    supplier_data = {
        'supplier_name': supplier_name,
        'supplier_id': 'CUSTOM_001',
        'lead_time_days': lead_time,
        'on_time_delivery_rate': on_time_rate,
        'defect_rate': defect_rate,
        'past_performance_score': past_score,
        'efficiency_score': (on_time_rate * (1 - defect_rate)) / (lead_time / 30),
        'quality_ratio': (1 - defect_rate) * past_score / 5,
        'delivery_score': on_time_rate * (60 / lead_time)
    }
    
    supplier_df = pd.DataFrame([supplier_data])
    
    # Get prediction
    X, _ = prepare_features(supplier_df)
    probs = model.predict(X)
    prediction = np.argmax(probs, axis=1)[0] + 1
    confidence = np.max(probs, axis=1)[0]
    
    print(f"\n=== SINGLE SUPPLIER EVALUATION ===")
    print(f"Supplier: {supplier_name}")
    print(f"Lead Time: {lead_time} days")
    print(f"On-Time Rate: {on_time_rate*100:.1f}%")
    print(f"Defect Rate: {defect_rate*100:.2f}%")
    print(f"Past Score: {past_score}/5")
    print(f"→ Predicted Relevance: {prediction}/5")
    print(f"→ Confidence: {confidence:.3f}")
    
    return prediction, confidence

# Run the main function
if __name__ == "__main__":
    results = main()
    
    print(f"\n🎯 New supplier evaluation completed!")
    print(f"📊 Check 'new_supplier_rankings.csv' for detailed results")
    print(f"💼 Ready for procurement decision making!")