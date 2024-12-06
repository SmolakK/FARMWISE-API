from main_call import read_data


def process_data(bounding_box, level, time_from, time_to, factors):
    # Wrapper around your existing read_data logic
    return read_data(bounding_box, level, time_from, time_to, factors)
