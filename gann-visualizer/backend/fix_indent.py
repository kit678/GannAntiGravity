with open('c:/Dev/GannTesting/gann-visualizer/backend/study_tool/angular_coverage_study.py', 'r') as f:
    lines = f.readlines()

for i in range(616, 665):
    if lines[i].startswith('                    '):
        lines[i] = lines[i][4:]

with open('c:/Dev/GannTesting/gann-visualizer/backend/study_tool/angular_coverage_study.py', 'w') as f:
    f.writelines(lines)
