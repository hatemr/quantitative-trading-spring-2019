def upload_data(start_date='2014-07-01'):
    cols = {'PAK':['3_Month','6_Month','1_Year','3_Year','5_Year'],
            'ROU':['6_Month','1_Year','3_Year','5_Year'],
            'IDN':['1_Year','2_Year','3_Year','4_Year','5_Year'], 
            'USA':['1_Month','3_Month','6_Month','1_Year','2_Year','3_Year','5_Year']}
    currencies = {'PAK':'CUR/PKR', 'ROU':'CUR/RON', 'IDN':'CUR/IDR'}  # foreign exchange rates
    
    data = dict()  # upload data
    
    libor = {'FRED/LIOR3M':'Libor_3M'}
    # Libor rates
    #df = fetch_quandl(l, start_date=start_date)  # from quandl
    #df = pd.read_csv('FRED_3M_Libor.csv').rename(columns={'DATE':'Date', 'USD3MTD156N':'Libor_3M'}).set_index('Date')  # via csv
    #df.index = pd.to_datetime(df.index)
    #df1 = df.resample('D').ffill().rename(columns={"Value": "Libor_3M"})
    #df1.Libor_3M = df1.Libor_3M.replace({'.':np.nan}).astype(np.float64).fillna(method='ffill')/100

    fr = Fred(api_key='50390f24fc44c3c608b53c9f35cbc53c',response_type='df')
    params = {'output_type':1,'observation_start':'2014-09-02','frequency':'wesu'}
    df = fr.series.observations('USD3MTD156N',params=params).drop(columns=['realtime_end', 'realtime_start']).rename(columns={'value':'Libor_3M','date':'Date'}) .set_index('Date').fillna(method='ffill')/100

    data[libor['FRED/LIOR3M']] = df
    
    i=0
    for country, col in cols.items():
        df = fetch_quandl('YC/'+country, start_date=start_date).rename(columns={'12-Month':'1-Year'})/100  # spot rates
        df.columns = [name.replace('-','_') for name in df.columns.tolist()]   # remove dashes "-"
        df1 = df.loc[:, cols[country]]
        df1['5_Year_spot'] = df1['5_Year'].copy()
        
        if country != 'USA':
            df4 = fetch_quandl(currencies[country], start_date=start_date).rename(columns={'RATE':'FX_rate'})  # get foregin exchange rates
            df1 = df1.merge(df4, how='left', left_index=True, right_index=True)
        
        #df1 = df1.resample('W-WED').last()
        
        df2 = df1.loc[:,cols[country]].T    # spot rates to zero rates
        cols2 = df2.index.tolist()
        df2.index = [int(name.replace('_Year','').replace('_Month','')) for name in cols[country]]
        df3 = compute_zcb_curve(df2).T
        df3.columns = cols2
        
        for c in cols[country]: df1[c] = df3[c].values  # replace spot with zero
        
        df1.columns = [name + '_' + country for name in df1.columns.tolist()]  # add suffixes to col names
        data3 = df1 if i==0 else data3.merge(df1, left_index=True, right_index=True)  # attach new country
        i+=1
        
        df1 = df1.merge(data[libor['FRED/LIOR3M']], left_index=True, right_index=True)
        
        data[country] = df1
    
    data3 = data3.merge(data[libor['FRED/LIOR3M']], how='left', left_index=True, right_index=True)   # add Libor
    
    return data3

########## ------------------ ##############



def carry_strategy(data, country1='PAK',country2='USA'):
    cols = {'PAK':['3_Month_PAK','6_Month_PAK','1_Year_PAK','3_Year_PAK','5_Year_PAK','5_Year_spot_PAK','FX_rate_PAK'],
            'ROU':['6_Month_ROU','1_Year_ROU','3_Year_ROU','5_Year_ROU', '5_Year_spot_ROU'],
            'IDN':['1_Year_IDN','2_Year_IDN','3_Year_IDN','4_Year_IDN','5_Year_IDN','5_Year_spot_IDN'], 
            'USA':['1_Month_USA','3_Month_USA','6_Month_USA','1_Year_USA','2_Year_USA','3_Year_USA','5_Year_USA','5_Year_spot_USA']}
    
    cols_two_countries = cols[country1]+cols[country2]+['Libor_3M']
    df = data.loc[:, cols_two_countries]
    df = df.assign(bp_today_PAK = 0.0)
    df = df.assign(bp_prev_PAK = 0.0)
    df = df.assign(bp_today_USA = 0.0)
    df = df.assign(bp_prev_USA = 0.0)
    df = df.assign(num_lending_close = 0.0)  # us closing out our lending position
    df = df.assign(num_lending_bought = 0.0)  # us lending    
    df = df.assign(num_borrow_sold = 0.0)  # us borrowing
    df = df.assign(num_borrow_close = 0.0)  # us closing out our borrowing position
    
    df = df.assign(cf_lending_close = 0.0)  # closing out our lending position
    df = df.assign(cf_lending_bought = 0.0)  # us lending
    df = df.assign(cf_borrow_sold = 0.0)  # us borrowing
    df = df.assign(cf_borrow_close = 0.0)  # us closing out our borrowing position
    
    
    cols_tenor = {'PAK':['3_Month_PAK','6_Month_PAK','1_Year_PAK','3_Year_PAK','5_Year_PAK'],
                  'ROU':['6_Month_ROU','1_Year_ROU','3_Year_ROU','5_Year_ROU'],
                  'IDN':['1_Year_IDN','2_Year_IDN','3_Year_IDN','4_Year_IDN','5_Year_IDN'], 
                  'USA':['1_Month_USA','3_Month_USA','6_Month_USA','1_Year_USA','2_Year_USA','3_Year_USA','5_Year_USA']}
    
    tenor_indices = {'PAK':[3/12, 6/12, 1, 3, 5],
                     'ROU':[6/12, 1, 3, 5],
                     'IDN':[1, 2, 3, 4, 5], 
                     'USA':[1/12,3/12,6/12,1,2,3,5]}
    
    for i in range(df.shape[0]):
        for country in [country1, country2]:
            rates = df.iloc[i].loc[cols_tenor[country]].copy()
            rates.index = tenor_indices[country]
            
            bond_price_today = bond_price(zcb=rates, coupon_rate= df.iloc[i].at['5_Year_spot_'+country], tenor=5)
            df.iat[i, np.where( df.columns.values=='bp_today_'+country)[0][0]] = bond_price_today
            
            if i!=0:
                bond_price_prev = bond_price(zcb=rates, coupon_rate=df.iloc[i-1].at['5_Year_spot_'+country], tenor=5-1/52)
                df.iloc[i].at['bp_prev_'+country] = bond_price_prev
                df.iat[i, np.where(df.columns.values=='bp_prev_'+country)[0][0]] = bond_price_prev
              
         # lending at high rate
        if i!=0:
            # close previous position
            df.iat[i, np.where(df.columns.values=='num_lending_close')[0][0]] = -df.iat[i-1, np.where(df.columns.values=='num_lending_bought')[0][0]]
        # lend money
        df.iat[i, np.where(df.columns.values=='num_lending_bought')[0][0]] = df.iat[i, np.where(df.columns.values=='FX_rate_'+country1)[0][0]] *1e7 / df.iat[i, np.where(df.columns.values=='bp_today_'+country1)[0][0]]
        
        # borrowing at low rate
        if i!=0:
            # close previous position
            df.iat[i, np.where(df.columns.values=='num_borrow_close')[0][0]] = -df.iat[i-1, np.where(df.columns.values=='num_borrow_sold')[0][0]]
        # borrow money (8MM USD)
        df.iat[i, np.where(df.columns.values=='num_borrow_sold')[0][0]] = -df.iat[i, np.where(df.columns.values=='FX_rate_'+country1)[0][0]] *8e6 / df.iat[i, np.where(df.columns.values=='bp_today_'+country2)[0][0]]
        
        # value
        df.iat[i, np.where(df.columns.values=='cf_lending_close')[0][0]] = -df.iat[i, np.where(df.columns.values=='num_lending_close')[0][0]] * df.iat[i, np.where(df.columns.values=='bp_prev_'+country1)[0][0]] / df.iat[i, np.where(df.columns.values=='FX_rate_'+country1)[0][0]]
        df.iat[i, np.where(df.columns.values=='cf_lending_bought')[0][0]] = -df.iat[i, np.where(df.columns.values=='num_lending_bought')[0][0]] * df.iat[i, np.where(df.columns.values=='bp_today_'+country1)[0][0]] / df.iat[i, np.where(df.columns.values=='FX_rate_'+country1)[0][0]]
        df.iat[i, np.where(df.columns.values=='cf_borrow_sold')[0][0]] = -df.iat[i, np.where(df.columns.values=='num_borrow_sold')[0][0]] * df.iat[i, np.where(df.columns.values=='bp_today_'+country2)[0][0]]
        df.iat[i, np.where(df.columns.values=='cf_borrow_close')[0][0]] = -df.iat[i, np.where(df.columns.values=='num_borrow_close')[0][0]] * df.iat[i, np.where(df.columns.values=='bp_today_'+country2)[0][0]]
        
    return df