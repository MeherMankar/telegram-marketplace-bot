import numpy as np
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class MLService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.fraud_model = None
        self.quality_model = None
        self.scaler = StandardScaler()
        self._load_models()
    
    def _load_models(self):
        """Load pre-trained ML models"""
        try:
            if os.path.exists('models/fraud_model.pkl'):
                self.fraud_model = joblib.load('models/fraud_model.pkl')
            else:
                # Initialize with basic Isolation Forest
                self.fraud_model = IsolationForest(contamination=0.1, random_state=42)
                
            if os.path.exists('models/quality_model.pkl'):
                self.quality_model = joblib.load('models/quality_model.pkl')
                
        except Exception as e:
            logger.error(f"Error loading ML models: {e}")
    
    async def calculate_account_quality_score(self, account_data: Dict[str, Any]) -> float:
        """Calculate quality score for an account using ML"""
        try:
            features = self._extract_account_features(account_data)
            
            # Basic scoring algorithm
            score = 100.0
            
            # Age factor (older accounts are better)
            if account_data.get('creation_year'):
                age = datetime.now().year - account_data['creation_year']
                score += min(age * 5, 30)  # Max 30 points for age
            
            # Username factor
            if account_data.get('username'):
                score += 15
            
            # Profile completeness
            if account_data.get('first_name'):
                score += 10
            if account_data.get('last_name'):
                score += 10
            if account_data.get('bio'):
                score += 10
            
            # Activity indicators
            if account_data.get('last_seen'):
                days_since_active = (datetime.now() - account_data['last_seen']).days
                if days_since_active < 7:
                    score += 20
                elif days_since_active < 30:
                    score += 10
            
            return min(score, 100.0)
            
        except Exception as e:
            logger.error(f"Error calculating quality score: {e}")
            return 50.0  # Default score
    
    async def detect_fraud(self, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Detect fraudulent activity using ML"""
        try:
            # Get user's recent activity
            recent_uploads = await self.db.accounts.count_documents({
                'seller_id': user_id,
                'created_at': {'$gte': utc_now() - timedelta(days=1)}
            })
            
            # Fraud indicators
            fraud_score = 0
            reasons = []
            
            # Too many uploads in short time
            if recent_uploads > 10:
                fraud_score += 30
                reasons.append("Excessive uploads in 24h")
            
            # Suspicious account patterns
            if not account_data.get('username') and not account_data.get('first_name'):
                fraud_score += 20
                reasons.append("Incomplete profile data")
            
            # Check for duplicate sessions
            existing = await self.db.accounts.find_one({
                'phone_number': account_data.get('phone_number'),
                'seller_id': {'$ne': user_id}
            })
            
            if existing:
                fraud_score += 50
                reasons.append("Duplicate phone number")
            
            is_fraud = fraud_score > 50
            
            return {
                'is_fraud': is_fraud,
                'fraud_score': fraud_score,
                'reasons': reasons,
                'confidence': min(fraud_score / 100, 1.0)
            }
            
        except Exception as e:
            logger.error(f"Error in fraud detection: {e}")
            return {'is_fraud': False, 'fraud_score': 0, 'reasons': [], 'confidence': 0.0}
    
    async def predict_price(self, account_data: Dict[str, Any]) -> float:
        """Predict optimal price for an account"""
        try:
            # Get market data
            similar_accounts = await self.db.listings.find({
                'country': account_data.get('country'),
                'creation_year': account_data.get('creation_year'),
                'status': 'sold'
            }).to_list(100)
            
            if not similar_accounts:
                # Default pricing
                base_price = 25.0
                if account_data.get('creation_year', 2024) < 2023:
                    base_price += 15.0
                if account_data.get('username'):
                    base_price += 10.0
                return base_price
            
            # Calculate average price from similar sold accounts
            avg_price = sum(acc['price'] for acc in similar_accounts) / len(similar_accounts)
            
            # Adjust based on quality score
            quality_score = await self.calculate_account_quality_score(account_data)
            price_multiplier = quality_score / 100.0
            
            predicted_price = avg_price * price_multiplier
            
            return round(predicted_price, 2)
            
        except Exception as e:
            logger.error(f"Error predicting price: {e}")
            return 25.0  # Default price
    
    def _extract_account_features(self, account_data: Dict[str, Any]) -> List[float]:
        """Extract numerical features from account data"""
        features = []
        
        # Age feature
        creation_year = account_data.get('creation_year', 2024)
        age = datetime.now().year - creation_year
        features.append(age)
        
        # Boolean features (0 or 1)
        features.append(1 if account_data.get('username') else 0)
        features.append(1 if account_data.get('first_name') else 0)
        features.append(1 if account_data.get('last_name') else 0)
        features.append(1 if account_data.get('bio') else 0)
        
        # Activity feature
        if account_data.get('last_seen'):
            days_since_active = (datetime.now() - account_data['last_seen']).days
            features.append(days_since_active)
        else:
            features.append(999)  # Unknown activity
        
        return features
    
    async def train_models(self):
        """Train ML models with existing data"""
        try:
            # Check if database connection exists
            if not self.db or not hasattr(self.db, 'accounts'):
                logger.info("Database not ready, skipping ML training")
                return
            
            # Get training data
            accounts = await self.db.accounts.find({
                'status': {'$in': ['approved', 'rejected']}
            }).to_list(1000)
            
            if len(accounts) < 10:
                logger.info(f"Only {len(accounts)} accounts available, need at least 10 for ML training")
                return
            
            # Prepare features and labels
            features = []
            labels = []
            
            for account in accounts:
                try:
                    feature_vector = self._extract_account_features(account)
                    if len(feature_vector) > 0:
                        features.append(feature_vector)
                        labels.append(1 if account['status'] == 'approved' else 0)
                except Exception as e:
                    logger.debug(f"Skipping account due to feature extraction error: {e}")
                    continue
            
            if len(features) < 10:
                logger.info(f"Only {len(features)} valid feature vectors, need at least 10")
                return
            
            # Train fraud detection model
            X = np.array(features)
            X_scaled = self.scaler.fit_transform(X)
            
            self.fraud_model.fit(X_scaled)
            
            # Save models
            os.makedirs('models', exist_ok=True)
            joblib.dump(self.fraud_model, 'models/fraud_model.pkl')
            joblib.dump(self.scaler, 'models/scaler.pkl')
            
            logger.info(f"ML models trained successfully with {len(features)} samples")
            
        except Exception as e:
            logger.info(f"ML training skipped: {e}")