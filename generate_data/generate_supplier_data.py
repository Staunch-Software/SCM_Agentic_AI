import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import seaborn as sns

# Set random seed for reproducibility
np.random.seed(42)

def generate_supplier_features(n_samples_per_class=10000):
    """
    Generate synthetic supplier data with realistic feature distributions
    that correlate with relevance scores
    """
    
    total_samples = n_samples_per_class * 5  # 5 relevance levels (1-5)
    samples_per_class = n_samples_per_class
    
    # Initialize arrays
    lead_times = []
    on_time_rates = []
    defect_rates = []
    past_scores = []
    relevance_scores = []
    
    # Generate data for each relevance level
    for relevance in range(1, 6):  # 1 to 5
        
        # Define parameters based on relevance level
        if relevance == 5:  # Excellent suppliers
            lead_time_params = (5, 15)    # Low lead time (5-15 days)
            on_time_params = (0.95, 0.99) # High on-time rate (95-99%)
            defect_params = (0.001, 0.01) # Very low defect rate (0.1-1%)
            past_score_params = (4.5, 5.0) # High past performance
            
        elif relevance == 4:  # Good suppliers
            lead_time_params = (10, 25)
            on_time_params = (0.85, 0.95)
            defect_params = (0.01, 0.03)
            past_score_params = (3.8, 4.5)
            
        elif relevance == 3:  # Average suppliers
            lead_time_params = (20, 40)
            on_time_params = (0.70, 0.85)
            defect_params = (0.03, 0.08)
            past_score_params = (3.0, 3.8)
            
        elif relevance == 2:  # Below average suppliers
            lead_time_params = (35, 60)
            on_time_params = (0.50, 0.70)
            defect_params = (0.08, 0.15)
            past_score_params = (2.0, 3.0)
            
        else:  # relevance == 1, Poor suppliers
            lead_time_params = (50, 90)
            on_time_params = (0.30, 0.50)
            defect_params = (0.15, 0.30)
            past_score_params = (1.0, 2.0)
        
        # Generate features for this relevance level
        for _ in range(samples_per_class):
            # Lead time (days) - higher is worse
            lead_time = np.random.uniform(lead_time_params[0], lead_time_params[1])
            lead_times.append(lead_time)
            
            # On-time delivery rate (0-1) - higher is better
            on_time_rate = np.random.uniform(on_time_params[0], on_time_params[1])
            on_time_rates.append(on_time_rate)
            
            # Defect rate (0-1) - lower is better
            defect_rate = np.random.uniform(defect_params[0], defect_params[1])
            defect_rates.append(defect_rate)
            
            # Past performance score (1-5) - higher is better
            past_score = np.random.uniform(past_score_params[0], past_score_params[1])
            past_scores.append(past_score)
            
            # Relevance score
            relevance_scores.append(relevance)
    
    # Create DataFrame
    df = pd.DataFrame({
        'lead_time_days': lead_times,
        'on_time_delivery_rate': on_time_rates,
        'defect_rate': defect_rates,
        'past_performance_score': past_scores,
        'relevance_score': relevance_scores
    })
    
    # Add some realistic noise and edge cases
    noise_factor = 0.1
    for col in ['lead_time_days', 'on_time_delivery_rate', 'defect_rate', 'past_performance_score']:
        noise = np.random.normal(0, noise_factor, len(df)) * df[col].std()
        df[col] += noise
    
    # Ensure bounds are respected
    df['on_time_delivery_rate'] = np.clip(df['on_time_delivery_rate'], 0, 1)
    df['defect_rate'] = np.clip(df['defect_rate'], 0, 1)
    df['past_performance_score'] = np.clip(df['past_performance_score'], 1, 5)
    df['lead_time_days'] = np.clip(df['lead_time_days'], 1, 120)
    
    # Add supplier IDs
    df['supplier_id'] = [f'SUP_{i:06d}' for i in range(1, len(df) + 1)]
    
    # Add some additional engineered features
    df['efficiency_score'] = (df['on_time_delivery_rate'] * (1 - df['defect_rate'])) / (df['lead_time_days'] / 30)
    df['quality_ratio'] = (1 - df['defect_rate']) * df['past_performance_score'] / 5
    df['delivery_score'] = df['on_time_delivery_rate'] * (60 / df['lead_time_days'])  # Normalize lead time impact
    
    # Shuffle the dataset
    df = df.sample(frac=1).reset_index(drop=True)
    
    return df

# Generate the dataset
print("Generating supplier dataset...")
supplier_data = generate_supplier_features(n_samples_per_class=10000)

print(f"Dataset shape: {supplier_data.shape}")
print(f"Total samples: {len(supplier_data)}")

# Display basic statistics
print("\n=== Dataset Summary ===")
print(supplier_data.describe())

print("\n=== Relevance Score Distribution ===")
print(supplier_data['relevance_score'].value_counts().sort_index())

# Display sample data
print("\n=== Sample Data ===")
print(supplier_data.head(10))

# Data quality checks
print("\n=== Data Quality Checks ===")
print(f"Missing values: {supplier_data.isnull().sum().sum()}")
print(f"Duplicate rows: {supplier_data.duplicated().sum()}")

# Feature correlations with target
print("\n=== Feature Correlations with Relevance Score ===")
feature_cols = ['lead_time_days', 'on_time_delivery_rate', 'defect_rate', 
                'past_performance_score', 'efficiency_score', 'quality_ratio', 'delivery_score']

correlations = supplier_data[feature_cols + ['relevance_score']].corr()['relevance_score'].sort_values(ascending=False)
print(correlations)

# Visualization code
def plot_data_analysis(df):
    """Create visualizations for data analysis"""
    
    plt.figure(figsize=(20, 15))
    
    # 1. Relevance score distribution
    plt.subplot(3, 4, 1)
    df['relevance_score'].value_counts().sort_index().plot(kind='bar', color='skyblue')
    plt.title('Relevance Score Distribution')
    plt.xlabel('Relevance Score')
    plt.ylabel('Count')
    
    # 2. Lead time by relevance
    plt.subplot(3, 4, 2)
    sns.boxplot(data=df, x='relevance_score', y='lead_time_days')
    plt.title('Lead Time by Relevance Score')
    
    # 3. On-time delivery by relevance
    plt.subplot(3, 4, 3)
    sns.boxplot(data=df, x='relevance_score', y='on_time_delivery_rate')
    plt.title('On-Time Delivery Rate by Relevance')
    
    # 4. Defect rate by relevance
    plt.subplot(3, 4, 4)
    sns.boxplot(data=df, x='relevance_score', y='defect_rate')
    plt.title('Defect Rate by Relevance Score')
    
    # 5. Past performance by relevance
    plt.subplot(3, 4, 5)
    sns.boxplot(data=df, x='relevance_score', y='past_performance_score')
    plt.title('Past Performance by Relevance')
    
    # 6. Correlation heatmap
    plt.subplot(3, 4, 6)
    feature_cols = ['lead_time_days', 'on_time_delivery_rate', 'defect_rate', 
                    'past_performance_score', 'relevance_score']
    corr_matrix = df[feature_cols].corr()
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0)
    plt.title('Feature Correlation Matrix')
    
    # 7. Efficiency score distribution
    plt.subplot(3, 4, 7)
    sns.boxplot(data=df, x='relevance_score', y='efficiency_score')
    plt.title('Efficiency Score by Relevance')
    
    # 8. Quality ratio distribution
    plt.subplot(3, 4, 8)
    sns.boxplot(data=df, x='relevance_score', y='quality_ratio')
    plt.title('Quality Ratio by Relevance')
    
    # 9. Delivery score distribution
    plt.subplot(3, 4, 9)
    sns.boxplot(data=df, x='relevance_score', y='delivery_score')
    plt.title('Delivery Score by Relevance')
    
    # 10. Lead time vs On-time rate colored by relevance
    plt.subplot(3, 4, 10)
    scatter = plt.scatter(df['lead_time_days'], df['on_time_delivery_rate'], 
                         c=df['relevance_score'], cmap='viridis', alpha=0.6)
    plt.colorbar(scatter)
    plt.xlabel('Lead Time (days)')
    plt.ylabel('On-Time Delivery Rate')
    plt.title('Lead Time vs On-Time Rate')
    
    # 11. Defect rate vs Past performance
    plt.subplot(3, 4, 11)
    scatter = plt.scatter(df['defect_rate'], df['past_performance_score'], 
                         c=df['relevance_score'], cmap='viridis', alpha=0.6)
    plt.colorbar(scatter)
    plt.xlabel('Defect Rate')
    plt.ylabel('Past Performance Score')
    plt.title('Defect Rate vs Past Performance')
    
    # 12. Overall score distribution
    plt.subplot(3, 4, 12)
    df['combined_score'] = (df['on_time_delivery_rate'] * df['past_performance_score'] * 
                           (1 - df['defect_rate']) / (df['lead_time_days'] / 30))
    sns.boxplot(data=df, x='relevance_score', y='combined_score')
    plt.title('Combined Score by Relevance')
    
    plt.tight_layout()
    plt.show()

# Create visualizations
print("\n=== Creating Data Visualizations ===")
plot_data_analysis(supplier_data)

# Save the dataset
supplier_data.to_csv('supplier_ranking_dataset.csv', index=False)
print(f"\nDataset saved as 'supplier_ranking_dataset.csv'")
print(f"Dataset contains {len(supplier_data)} suppliers with balanced relevance scores")

# Show feature statistics by relevance level
print("\n=== Feature Statistics by Relevance Level ===")
for score in range(1, 6):
    subset = supplier_data[supplier_data['relevance_score'] == score]
    print(f"\nRelevance Score {score} (n={len(subset)}):")
    print(f"  Lead Time: {subset['lead_time_days'].mean():.1f} ± {subset['lead_time_days'].std():.1f} days")
    print(f"  On-Time Rate: {subset['on_time_delivery_rate'].mean():.3f} ± {subset['on_time_delivery_rate'].std():.3f}")
    print(f"  Defect Rate: {subset['defect_rate'].mean():.4f} ± {subset['defect_rate'].std():.4f}")
    print(f"  Past Score: {subset['past_performance_score'].mean():.2f} ± {subset['past_performance_score'].std():.2f}")