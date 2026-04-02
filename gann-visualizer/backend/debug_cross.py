def check():
    c_open = 23079.80
    c_close = 23092.35
    c_high = 23097.45
    c_low = 23060.65
    
    prev_close = 23078.95
    line_price = 23072.80
    prev_line_price = 23082.00
    
    is_cross_up = prev_close <= prev_line_price and c_close > line_price
    print(f"is_cross_up = {is_cross_up}")

check()
