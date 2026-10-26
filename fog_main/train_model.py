import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from imblearn.under_sampling import RandomUnderSampler
from imblearn.over_sampling import SMOTE

print("1. Loading the 4-Class KNIME dataset...")
# Ensure this matches the exact filename you exported from KNIME
df = pd.read_csv("CIVILEA_4Class_Master_Training.csv") 

# Define the exact inputs expected from the ESP32 edge layer
feature_cols = ['distance_cm', 'rain_raw', 'flow_rate_l_min', 'soil_raw', 'tds_voltage']
X = df[feature_cols]
y = df['flood_risk_level']

print("2. Splitting data (80% Train, 20% Test) to prevent data leakage...")
# stratify=y ensures the 20% test set gets a fair slice of the rare classes
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print("3. Handling Class Imbalance in Training Data...")
# Step A: Undersample the massive Class 0 down to 2,500 rows to match the others
under = RandomUnderSampler(sampling_strategy={0: 2500}, random_state=42)
X_train_under, y_train_under = under.fit_resample(X_train, y_train)

# Step B: Use SMOTE to inflate Classes 1, 2, and 3 so everything sits exactly at 2,500
smote = SMOTE(random_state=42, k_neighbors=3)
X_train_balanced, y_train_balanced = smote.fit_resample(X_train_under, y_train_under)

print("4. Training XGBoost Multi-Class Gatekeeper...")
model = xgb.XGBClassifier(
    objective='multi:softmax',
    num_class=4,             # Now handling Safe, Warning, Danger, and Fault
    max_depth=5,             # Kept slightly shallow for faster Pi execution
    n_estimators=150,
    learning_rate=0.1,
    random_state=42,
    eval_metric='mlogloss'
)

model.fit(X_train_balanced, y_train_balanced)

print("5. Evaluating on pure, untouched Test Data...")
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
print(f"\n--- OVERALL REAL-TIME ACCURACY: {accuracy * 100:.2f}% ---")
print("\n--- DETAILED CLASSIFICATION REPORT ---")
print(classification_report(y_test, y_pred, digits=4))
print("--- CONFUSION MATRIX ---")
print(confusion_matrix(y_test, y_pred))

model_filename = "fog_gatekeeper_xgboost.json"
model.save_model(model_filename)
print(f"\nModel successfully saved for production as: {model_filename}")
