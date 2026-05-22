import os
import sys
import json
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import xgboost as xgb
from pymongo import MongoClient

# Custom .env loader to avoid dependencies on python-dotenv
def load_env(filepath):
    if os.path.exists(filepath):
        print(f"Loading environment from {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip("'").strip('"')
                    os.environ[key.strip()] = val

# Load Sails .env file
sails_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_env(os.path.join(sails_root, '.env'))

# Define locations list
ALL_LOCATIONS = [
    'JJSC', 'SSSC', 'WSSC', 'BTSC', 'NHSC', 'SLSC', 'ZSSC', 'DTSC', 'NGSC', 'LKSC',
    'TYSC', 'SCSC', 'LZSC', 'XZSC', 'PQFN', 'RFFN', 'ZBSC', 'NTSC', 'CMSC', 'SJRF'
]

# Cache for holiday data
HOLIDAY_CACHE = {}

def get_holidays_for_year(year):
    """Fetch Taiwan holidays from JSdelivr CDN, fallback to local JSON files."""
    if year in HOLIDAY_CACHE:
        return HOLIDAY_CACHE[year]
    
    # Try fetching online first
    url = f"https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"
    try:
        print(f"Fetching holidays online for {year} from: {url}")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            holidays = {item['date'] for item in data if item.get('isHoliday') is True}
            HOLIDAY_CACHE[year] = holidays
            print(f"Successfully loaded online holidays for {year} ({len(holidays)} days)")
            return holidays
    except Exception as e:
        print(f"Online holiday fetch failed for {year}: {e}. Trying local fallback.")
    
    # Try local fallback
    local_path = os.path.join(os.path.dirname(__file__), f"holiday/{year}.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                holidays = {item['date'] for item in data if item.get('isHoliday') is True}
                HOLIDAY_CACHE[year] = holidays
                print(f"Successfully loaded local holidays fallback for {year} ({len(holidays)} days)")
                return holidays
        except Exception as le:
            print(f"Failed to read local holiday file: {le}")
            
    HOLIDAY_CACHE[year] = set()
    return set()

def is_holiday_datetime(dt):
    """Determine if a datetime is a holiday in Taiwan."""
    date_str = dt.strftime("%Y%m%d")
    return date_str in get_holidays_for_year(dt.year)

def get_database_name(url_str):
    """Parse database name from MongoDB connection string."""
    try:
        parsed = urlparse(url_str)
        path = parsed.path.strip('/')
        if path:
            return path
    except Exception:
        pass
    return "sports_center"

def load_data():
    """Connect to MongoDB to load historical data, with local CSV fallback."""
    mongo_url = os.getenv("MONGODB")
    db_name = None
    client = None
    db = None
    loaded_from_mongo = False
    df = pd.DataFrame()
    
    # 1. Try Remote / Local MongoDB
    if mongo_url:
        try:
            print(f"Attempting to connect to MongoDB URI...")
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db_name = get_database_name(mongo_url)
            db = client[db_name]
            print(f"Connected successfully to MongoDB database: {db_name}")
        except Exception as e:
            print(f"MongoDB connection failed: {e}. Trying local MongoDB fallback...")
            
    if db is None:
        try:
            client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
            client.admin.command('ping')
            db = client['equip'] # Fallback to local 'equip' database
            print("Connected successfully to local MongoDB fallback on localhost:27017")
        except Exception as e:
            print(f"Local MongoDB connection also failed: {e}")
            
    # 2. Try loading from MongoDB collection
    if db is not None:
        try:
            # Query last 90 days to avoid loading too much data into memory
            cutoff_date = datetime.now() - timedelta(days=90)
            print(f"Querying MongoDB 'data' collection for records since {cutoff_date}...")
            
            # Use 'data' collection (parallel to Data model)
            records = []
            cursor = db.data.find({"time": {"$gte": cutoff_date}}).sort("time", 1)
            
            for doc in cursor:
                t = doc.get("time")
                if not t:
                    continue
                loc_people = doc.get("locationPeople", [])
                for lp in loc_people:
                    records.append({
                        "location": lp.get("short"),
                        "peoNum": lp.get("peoNum"),
                        "maxPeo": lp.get("maxPeo"),
                        "time": t
                    })
            
            if records:
                df = pd.DataFrame(records)
                print(f"Successfully loaded {len(df)} records from MongoDB.")
                loaded_from_mongo = True
            else:
                print("MongoDB 'data' collection is empty or has no records in date range.")
        except Exception as e:
            print(f"Error reading collection from MongoDB: {e}")
            
    # 3. Fallback to Local CSV
    if not loaded_from_mongo:
        csv_path = os.path.join(os.path.dirname(__file__), 'output_MARCH2026.csv')
        print(f"Loading data from local fallback CSV: {csv_path}")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                df['time'] = pd.to_datetime(df['time'])
                print(f"Loaded {len(df)} records from CSV.")
            except Exception as e:
                print(f"Failed to read local fallback CSV: {e}")
                sys.exit(1)
        else:
            print(f"Fallback CSV not found at {csv_path}. Exiting.")
            sys.exit(1)
            
    # Clean data columns
    df['peoNum'] = pd.to_numeric(df['peoNum'], errors='coerce')
    if 'maxPeo' in df.columns:
        df['maxPeo'] = pd.to_numeric(df['maxPeo'], errors='coerce')
    else:
        df['maxPeo'] = 100
    df['peoNum'] = df['peoNum'].fillna(0)
    df['maxPeo'] = df['maxPeo'].fillna(100)
    
    return df, db

def preprocess_data(df):
    """Interpolate and align timestamps to a uniform 15-minute grid."""
    print("Preprocessing time series data...")
    # Convert 'time' to datetime if it isn't
    df['time'] = pd.to_datetime(df['time'])
    
    # Drop duplicates
    df = df.drop_duplicates(subset=['time', 'location'])
    
    # Keep only defined locations
    df = df[df['location'].isin(ALL_LOCATIONS)]
    
    # Pivot to align timelines
    pivoted = df.pivot(index='time', columns='location', values='peoNum')
    
    # Resample to 15-minute grid, interpolate small gaps (up to 1 hour), and forward fill
    pivoted = pivoted.resample('15min').mean().interpolate(method='linear', limit=4).ffill(limit=4)
    
    # Get latest maxPeo map
    latest_max_peo = df.groupby('location')['maxPeo'].last().to_dict()
    
    # Melt back to long format
    df_clean = pivoted.reset_index().melt(id_vars='time', value_name='peoNum')
    df_clean['maxPeo'] = df_clean['location'].map(latest_max_peo).fillna(100)
    
    return df_clean

def sync_locations(db):
    """Query 'locations' collection from MongoDB, dynamically update ALL_LOCATIONS and return coordinates map."""
    global ALL_LOCATIONS
    coords = {}
    
    # 1. Try querying from MongoDB locations collection
    if db is not None:
        try:
            print("Querying 'locations' collection from MongoDB for coordinates...")
            cursor = db.locations.find({})
            db_locs = list(cursor)
            if db_locs:
                db_shorts = []
                for loc in db_locs:
                    short = loc.get('short')
                    pos = loc.get('position', {})
                    if short and pos and 'coordinates' in pos:
                        db_shorts.append(short)
                        coords[short] = {
                            'lat': pos['coordinates'][0],
                            'lon': pos['coordinates'][1]
                        }
                if db_shorts:
                    # Merge and preserve order, avoiding duplicates
                    merged_locations = list(ALL_LOCATIONS)
                    for sh in db_shorts:
                        if sh not in merged_locations:
                            merged_locations.append(sh)
                    ALL_LOCATIONS = merged_locations
                    print(f"Dynamically loaded locations from DB: {db_shorts}")
                    print(f"Updated ALL_LOCATIONS (total {len(ALL_LOCATIONS)}): {ALL_LOCATIONS}")
                    return coords
        except Exception as e:
            print(f"Failed to query locations collection: {e}. Falling back to local configuration.")
            
    # 2. Fallback to local sports_center.locations.json
    locations_path = os.path.join(os.path.dirname(__file__), 'sports_center.locations.json')
    if os.path.exists(locations_path):
        try:
            with open(locations_path, 'r', encoding='utf-8') as f:
                locations_data = json.load(f)
            for loc in locations_data:
                short = loc.get('short')
                pos = loc.get('position', {})
                if short and pos and 'coordinates' in pos:
                    coords[short] = {
                        'lat': pos['coordinates'][0],
                        'lon': pos['coordinates'][1]
                    }
            print(f"Loaded {len(coords)} coordinates from local JSON fallback.")
        except Exception as e:
            print(f"Error loading local locations JSON fallback: {e}")
            
    return coords

def fetch_weather_data(coords):
    """Fetch weather data from Open-Meteo for all sports center coordinates."""
    if not coords:
        print("No coordinates mapping provided. Cannot fetch weather.")
        return {}
        
    # Form batch request URL
    ordered_shorts = [loc for loc in ALL_LOCATIONS if loc in coords]
    if not ordered_shorts:
        print("No matching locations found in coordinates mapping.")
        return {}
        
    latitudes = [str(coords[loc]['lat']) for loc in ordered_shorts]
    longitudes = [str(coords[loc]['lon']) for loc in ordered_shorts]
    
    lat_str = ",".join(latitudes)
    lon_str = ",".join(longitudes)
    
    # past_days=92 covers the last 3 months, forecast_days=3 covers the next 48 hours
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat_str}&longitude={lon_str}&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum&timezone=Asia%2FTaipei&past_days=92&forecast_days=3"
    
    weather_by_loc = {}
    try:
        print(f"Querying weather forecast from Open-Meteo: {url}")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        if not isinstance(res_data, list):
            res_data = [res_data]
            
        for idx, short in enumerate(ordered_shorts):
            loc_weather = res_data[idx]
            daily = loc_weather.get('daily', {})
            times = daily.get('time', [])
            t_max = daily.get('temperature_2m_max', [])
            t_min = daily.get('temperature_2m_min', [])
            t_mean = daily.get('temperature_2m_mean', [])
            precip = daily.get('precipitation_sum', [])
            
            weather_by_loc[short] = {}
            for day_idx, date_str in enumerate(times):
                try:
                    p_sum = precip[day_idx] if (day_idx < len(precip) and precip[day_idx] is not None) else 0.0
                    # Categorize subjective precipitation (0 to 5) aligned with CWA definitions:
                    # 0: 無降雨, 1: 微量降雨 (<= 2mm), 2: 小雨 (<= 10mm), 3: 中雨 (<= 40mm), 4: 大雨 (<= 80mm), 5: 豪大雨 (> 80mm)
                    if p_sum == 0:
                        p_cat = 0
                    elif p_sum <= 2.0:
                        p_cat = 1
                    elif p_sum <= 10.0:
                        p_cat = 2
                    elif p_sum <= 40.0:
                        p_cat = 3
                    elif p_sum <= 80.0:
                        p_cat = 4
                    else:
                        p_cat = 5
                        
                    weather_by_loc[short][date_str] = {
                        'max_temp': t_max[day_idx] if (day_idx < len(t_max) and t_max[day_idx] is not None) else 25.0,
                        'min_temp': t_min[day_idx] if (day_idx < len(t_min) and t_min[day_idx] is not None) else 18.0,
                        'avg_temp': t_mean[day_idx] if (day_idx < len(t_mean) and t_mean[day_idx] is not None) else 22.0,
                        'precipitation_sum': p_sum,
                        'precipitation_category': p_cat
                    }
                except (IndexError, TypeError):
                    pass
        print(f"Successfully loaded weather for {len(weather_by_loc)} centers.")
    except Exception as e:
        print(f"Warning: Failed to fetch weather data: {e}. Using offline defaults.")
        
    return weather_by_loc

def compute_prediction_metadata(X_pred, contribs, weather_data, df_pred_original):
    """
    Compute dominant factors, breakdown percentages, and map weather info for each prediction.
    """
    feature_names = X_pred.columns.tolist()
    
    # Define categories of features
    categories = {
        '歷史人流慣性': ['lag_yesterday', 'lag_2days_ago', 'lag_last_week', 'lag_yesterday_trend'],
        '時間與星期': ['Time_sin', 'Time_cos', 'DayOfWeek_sin', 'DayOfWeek_cos', 'is_weekend', 'hour', 'minute', 'dayofweek'],
        '場館基本屬性': ['maxPeo'] + [col for col in feature_names if col.startswith('location_')],
        '假日與節慶': ['isHoliday'],
        '氣溫因素': ['max_temp', 'min_temp', 'avg_temp'],
        '降雨因素': ['precipitation_sum', 'precipitation_category']
    }
    
    # Find feature indices for each category
    cat_indices = {}
    for cat_name, cols in categories.items():
        cat_indices[cat_name] = [feature_names.index(col) for col in cols if col in feature_names]
        
    num_samples = len(X_pred)
    metadata_list = []
    
    # Prepare Taiwan local timezone date strings
    times = df_pred_original['time']
    if times.dt.tz is None:
        local_times = times.dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
    else:
        local_times = times.dt.tz_convert('Asia/Taipei')
    date_strs = local_times.dt.strftime("%Y-%m-%d")
    
    for i in range(num_samples):
        loc = df_pred_original.iloc[i]['location']
        dt_str = date_strs.iloc[i]
        
        # 1. Fetch weather info
        weather_info = {
            'temp': 22.0,
            'min_temp': 18.0,
            'max_temp': 25.0,
            'precipitation': 0.0,
            'precipitation_category': '無降雨'
        }
        
        w = None
        if weather_data and loc in weather_data:
            w = weather_data[loc].get(dt_str)
        if w:
            p_cat_map = {0: '無降雨', 1: '微量降雨', 2: '小雨', 3: '中雨', 4: '大雨', 5: '豪大雨'}
            weather_info = {
                'temp': float(w['avg_temp']),
                'min_temp': float(w['min_temp']),
                'max_temp': float(w['max_temp']),
                'precipitation': float(w['precipitation_sum']),
                'precipitation_category': p_cat_map.get(w['precipitation_category'], '無降雨')
            }
            
        # 2. Calculate category contributions
        cat_vals = {}
        total_abs = 0.0
        for cat_name, indices in cat_indices.items():
            val = sum(abs(contribs[i][idx]) for idx in indices)
            cat_vals[cat_name] = val
            total_abs += val
            
        if total_abs > 0:
            cat_pcts = {k: float(round((v / total_abs) * 100, 1)) for k, v in cat_vals.items()}
            dom_cat = max(cat_vals, key=cat_vals.get)
            dom_pct = cat_pcts[dom_cat]
            dominant_factor = f"{dom_cat} ({dom_pct}%)"
        else:
            cat_pcts = {k: 0.0 for k in cat_vals.keys()}
            cat_pcts['歷史人流慣性'] = 100.0
            dominant_factor = "歷史人流慣性 (100.0%)"
            
        metadata_list.append({
            'dominantFactor': dominant_factor,
            'weather': weather_info,
            'factors': cat_pcts
        })
        
    return metadata_list

def build_features(df, weather_data=None):
    """Build time, holiday, weather, and lag features."""
    df = df.copy()
    
    # Localize time to Taiwan timezone (Asia/Taipei) for calendar calculations
    if df['time'].dt.tz is None:
        local_time = df['time'].dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
    else:
        local_time = df['time'].dt.tz_convert('Asia/Taipei')
        
    df['hour'] = local_time.dt.hour
    df['minute'] = local_time.dt.minute
    df['dayofweek'] = local_time.dt.dayofweek
    df['is_weekend'] = (df['dayofweek'] >= 5).astype(int)
    df['isHoliday'] = local_time.apply(lambda x: 1 if is_holiday_datetime(x) else 0)
    
    # Cyclical encodings for hour/minute and day of week
    minutes_since_midnight = df['hour'] * 60 + df['minute']
    df['Time_sin'] = np.sin(2 * np.pi * minutes_since_midnight / 1440.0)
    df['Time_cos'] = np.cos(2 * np.pi * minutes_since_midnight / 1440.0)
    
    df['DayOfWeek_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7.0)
    df['DayOfWeek_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7.0)
    
    # Map daily weather features
    date_strs = local_time.dt.strftime("%Y-%m-%d")
    
    max_temps = []
    min_temps = []
    avg_temps = []
    precip_sums = []
    precip_cats = []
    
    for idx, row in df.iterrows():
        loc = row['location']
        dt_str = date_strs.iloc[idx]
        
        w = None
        if weather_data and loc in weather_data:
            w = weather_data[loc].get(dt_str)
            
        if w:
            max_temps.append(w['max_temp'])
            min_temps.append(w['min_temp'])
            avg_temps.append(w['avg_temp'])
            precip_sums.append(w['precipitation_sum'])
            precip_cats.append(w['precipitation_category'])
        else:
            # Fallback to local row fields if available, e.g. from local CSV
            row_max = row.get('max_temp', 25.0)
            row_min = row.get('min_temp', 18.0)
            row_avg = row.get('avg_temp', 22.0)
            
            p_sum = row.get('precipitation_sum', row.get('precipitation', 0.0))
            if pd.isna(p_sum):
                p_sum = 0.0
                
            p_cat = row.get('precipitation_category', None)
            if p_cat is None or pd.isna(p_cat):
                sub_p_cat = row.get('subjective_precipitation_category', None)
                if sub_p_cat is not None and not pd.isna(sub_p_cat):
                    # Map old (0,1,2,3) to new (0,1,2,3,4,5)
                    p_cat = int(sub_p_cat)
                else:
                    p_cat = 0
            else:
                p_cat = int(p_cat)
                
            max_temps.append(row_max if not pd.isna(row_max) else 25.0)
            min_temps.append(row_min if not pd.isna(row_min) else 18.0)
            avg_temps.append(row_avg if not pd.isna(row_avg) else 22.0)
            precip_sums.append(p_sum)
            precip_cats.append(p_cat)
            
    df['max_temp'] = max_temps
    df['min_temp'] = min_temps
    df['avg_temp'] = avg_temps
    df['precipitation_sum'] = precip_sums
    df['precipitation_category'] = precip_cats
    
    # Sort for lag operations
    df = df.sort_values(by=['location', 'time']).reset_index(drop=True)
    
    # 15 minutes step. 1 day = 96 steps, 2 days = 192 steps, 7 days = 672 steps
    df['lag_yesterday'] = df.groupby('location')['peoNum'].shift(96)
    df['lag_2days_ago'] = df.groupby('location')['peoNum'].shift(192)
    df['lag_last_week'] = df.groupby('location')['peoNum'].shift(672)
    
    # yesterday trend: rolling average of yesterday's occupancy around this hour
    df['lag_yesterday_trend'] = df.groupby('location')['lag_yesterday'].transform(
        lambda x: x.rolling(window=4, min_periods=1).mean()
    )
    
    return df

def main():
    print("--- Starting Weather-Aware Occupancy Retraining and Prediction Pipeline ---")
    df_raw, db = load_data()
    
    if df_raw.empty:
        print("Error: Historical dataset is empty. Cannot train model.")
        sys.exit(1)
        
    # Sync locations and coordinates from MongoDB locations collection
    coords = sync_locations(db)
    
    # Fetch real-time weather forecasts and history
    weather_data = fetch_weather_data(coords)
        
    df_clean = preprocess_data(df_raw)
    
    print("Building features for training dataset...")
    df_features = build_features(df_clean, weather_data=weather_data)
    
    # Drop rows where target label or lags are NaN (first 7 days of historical timeline)
    train_df = df_features.dropna(subset=['peoNum', 'lag_last_week']).copy()
    if len(train_df) < 500:
        print("Warning: Insufficient historical rows after lag calculations. Training on all available.")
        train_df = df_features.dropna(subset=['peoNum', 'lag_yesterday']).copy()
        
    if train_df.empty:
        print("Error: No training features could be built. Please verify you have at least 7 days of history.")
        sys.exit(1)
        
    print(f"Training dataset size: {train_df.shape[0]} samples")
    
    # Create location One-Hot encoded dummy columns
    train_df_encoded = pd.get_dummies(train_df, columns=['location'], drop_first=False)
    location_cols = [f'location_{loc}' for loc in ALL_LOCATIONS]
    for col in location_cols:
        if col not in train_df_encoded.columns:
            train_df_encoded[col] = 0
            
    feature_cols = [
        'Time_sin', 'Time_cos', 'DayOfWeek_sin', 'DayOfWeek_cos', 'is_weekend', 'isHoliday', 'maxPeo',
        'lag_yesterday', 'lag_2days_ago', 'lag_last_week', 'lag_yesterday_trend',
        'max_temp', 'min_temp', 'avg_temp', 'precipitation_sum', 'precipitation_category'
    ] + location_cols
    
    X_train = train_df_encoded[feature_cols]
    y_train = train_df_encoded['peoNum']
    
    print("Training XGBoost Regressor...")
    model = xgb.XGBRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)
    print("XGBoost model training completed successfully!")
    
    # --- Generate Predictions for next 48 Hours ---
    T_max = df_clean['time'].max()
    print(f"Latest historical timestamp in data: {T_max}")
    
    # Construct prediction timezone index
    future_times = pd.date_range(
        start=T_max + pd.Timedelta(minutes=15),
        end=T_max + pd.Timedelta(hours=48),
        freq='15min'
    )
    print(f"Projecting predictions for {len(future_times)} intervals ({future_times[0]} to {future_times[-1]})")
    
    # Generate rows for all locations
    latest_max_peo = df_clean.groupby('location')['maxPeo'].last().to_dict()
    future_rows = []
    for t in future_times:
        for loc in ALL_LOCATIONS:
            future_rows.append({
                'time': t,
                'location': loc,
                'peoNum': np.nan,
                'maxPeo': latest_max_peo.get(loc, 100)
            })
    future_df = pd.DataFrame(future_rows)
    
    # Keep only the last 8 days of history to compute lags for the future window
    history_subset = df_clean[df_clean['time'] > (T_max - pd.Timedelta(days=8))].copy()
    combined = pd.concat([history_subset, future_df], ignore_index=True)
    combined = combined.sort_values(by=['location', 'time']).reset_index(drop=True)
    
    # Step 1: Predict first 24 hours of future timeline (uses actual lags from history)
    print("Step 1: Forecasting first 24h window...")
    combined_features = build_features(combined, weather_data=weather_data)
    first_24h_mask = (combined_features['time'] > T_max) & (combined_features['time'] <= T_max + pd.Timedelta(hours=24))
    first_24h_df = combined_features[first_24h_mask].copy()
    
    first_24h_df_encoded = pd.get_dummies(first_24h_df, columns=['location'], drop_first=False)
    for col in location_cols:
        if col not in first_24h_df_encoded.columns:
            first_24h_df_encoded[col] = 0
            
    X_pred_1 = first_24h_df_encoded[feature_cols]
    preds_1 = model.predict(X_pred_1)
    preds_1 = np.clip(preds_1, 0, first_24h_df['maxPeo'].values)
    preds_1 = np.round(preds_1)
    
    # Contributions and factor breakdown
    dmat_1 = xgb.DMatrix(X_pred_1)
    contribs_1 = model.get_booster().predict(dmat_1, pred_contribs=True)
    metadata_1 = compute_prediction_metadata(X_pred_1, contribs_1, weather_data, first_24h_df)
    
    # Update combined dataframe with step 1 predictions & metadata
    first_24h_df['peoNum'] = preds_1
    first_24h_df['dominantFactor'] = [m['dominantFactor'] for m in metadata_1]
    first_24h_df['weather'] = [m['weather'] for m in metadata_1]
    first_24h_df['factors'] = [m['factors'] for m in metadata_1]
    
    combined['dominantFactor'] = None
    combined['weather'] = None
    combined['factors'] = None
    
    combined.set_index(['location', 'time'], inplace=True)
    first_24h_df.set_index(['location', 'time'], inplace=True)
    combined.update(first_24h_df[['peoNum', 'dominantFactor', 'weather', 'factors']])
    combined.reset_index(inplace=True)
    
    # Step 2: Predict second 24 hours of future timeline (uses predicted lags from step 1)
    print("Step 2: Forecasting second 24h window (recursive)...")
    combined_features_2 = build_features(combined, weather_data=weather_data)
    second_24h_mask = (combined_features_2['time'] > T_max + pd.Timedelta(hours=24)) & (combined_features_2['time'] <= T_max + pd.Timedelta(hours=48))
    second_24h_df = combined_features_2[second_24h_mask].copy()
    
    second_24h_df_encoded = pd.get_dummies(second_24h_df, columns=['location'], drop_first=False)
    for col in location_cols:
        if col not in second_24h_df_encoded.columns:
            second_24h_df_encoded[col] = 0
            
    X_pred_2 = second_24h_df_encoded[feature_cols]
    preds_2 = model.predict(X_pred_2)
    preds_2 = np.clip(preds_2, 0, second_24h_df['maxPeo'].values)
    preds_2 = np.round(preds_2)
    
    # Contributions and factor breakdown
    dmat_2 = xgb.DMatrix(X_pred_2)
    contribs_2 = model.get_booster().predict(dmat_2, pred_contribs=True)
    metadata_2 = compute_prediction_metadata(X_pred_2, contribs_2, weather_data, second_24h_df)
    
    # Update combined dataframe with step 2 predictions & metadata
    second_24h_df['peoNum'] = preds_2
    second_24h_df['dominantFactor'] = [m['dominantFactor'] for m in metadata_2]
    second_24h_df['weather'] = [m['weather'] for m in metadata_2]
    second_24h_df['factors'] = [m['factors'] for m in metadata_2]
    
    combined.set_index(['location', 'time'], inplace=True)
    second_24h_df.set_index(['location', 'time'], inplace=True)
    combined.update(second_24h_df[['peoNum', 'dominantFactor', 'weather', 'factors']])
    combined.reset_index(inplace=True)
    
    # --- Format and Save Predictions ---
    pred_only = combined[combined['time'] > T_max].copy()
    prediction_docs = []
    
    # Group by prediction timestamp and structure to match actual data model
    for t, group in pred_only.groupby('time'):
        location_people = []
        for idx, row in group.iterrows():
            location_people.append({
                'short': row['location'],
                'peoNum': int(row['peoNum']),
                'maxPeo': int(row['maxPeo']),
                'dominantFactor': row['dominantFactor'] if row['dominantFactor'] else '歷史人流慣性 (100.0%)',
                'weather': row['weather'] if row['weather'] else {
                    'temp': 22.0, 'min_temp': 18.0, 'max_temp': 25.0, 'precipitation': 0.0, 'precipitation_category': '無降雨'
                },
                'factors': row['factors'] if row['factors'] else {
                    '歷史人流慣性': 100.0, '時間與星期': 0.0, '場館基本屬性': 0.0, '假日與節慶': 0.0, '氣溫因素': 0.0, '降雨因素': 0.0
                }
            })
        
        # Keep time timezone-naive in UTC for MongoDB standard
        utc_time = t.to_pydatetime()
        prediction_docs.append({
            'time': utc_time,
            'locationPeople': location_people
        })
        
    print(f"Formed {len(prediction_docs)} predicted timestamp intervals.")
    
    # Save to MongoDB if available, otherwise write local json file for backup
    if db is not None:
        try:
            predictions_col = db['predictions']
            # Delete outdated predictions
            predictions_col.delete_many({})
            # Write new predictions
            if prediction_docs:
                predictions_col.insert_many(prediction_docs)
            print(f"Success: Wrote predictions to MongoDB collection 'predictions'.")
        except Exception as e:
            print(f"Error saving predictions to MongoDB: {e}")
            write_local_backup(prediction_docs)
    else:
        print("No database connection. Saving local backup file.")
        write_local_backup(prediction_docs)

def write_local_backup(prediction_docs):
    """Save predictions locally in JSON format when DB is offline."""
    backup_path = os.path.join(os.path.dirname(__file__), 'predictions_backup.json')
    try:
        # Convert datetime to string for json serialization
        serialized = []
        for doc in prediction_docs:
            serialized.append({
                'time': doc['time'].isoformat(),
                'locationPeople': doc['locationPeople']
            })
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)
        print(f"Local backup written successfully to {backup_path}")
    except Exception as e:
        print(f"Failed to write local backup JSON: {e}")

if __name__ == '__main__':
    main()
