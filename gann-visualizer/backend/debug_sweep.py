from study_tool.intersection_detector import IntersectionEvent
e = IntersectionEvent('fan', 'line', 'P1', 0.875, 12345, 100.0, 'cross')
print(getattr(e, 'prev_price', 'Missing'))
e.prev_price = 90.0
print(getattr(e, 'prev_price', 'Missing'))
