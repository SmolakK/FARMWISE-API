from utils.country_bboxes import return_country_bboxes


def merge_bounding_boxes(bboxes):
    north = max(b[0] for b in bboxes)
    south = min(b[1] for b in bboxes)
    east = max(b[2] for b in bboxes)
    west = min(b[3] for b in bboxes)
    return north, south, east, west
