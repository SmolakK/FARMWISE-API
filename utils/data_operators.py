def flatten_list(nested_list):
    flattened = []
    for item in nested_list:
        if isinstance(item, list):
            flattened.extend(flatten_list(item))  # Recursively flatten if the item is a list
        else:
            flattened.append(item)
    return flattened
