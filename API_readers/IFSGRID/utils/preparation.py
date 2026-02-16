from datetime import datetime, date

def check_overlap(period):

    start = datetime.strptime(period[0], "%Y-%m-%d").date()
    end = datetime.strptime(period[1], "%Y-%m-%d").date()
    
    boundary_start = date(2020, 1, 1)
    today = date.today()

    if end >= boundary_start:
        new_start = max(start, boundary_start)
        return new_start, end
    else:
        return None, None
