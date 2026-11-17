"""Card markings as booleans, never personal identifier values."""
import re


def identity_markers(text):
    markers=[]
    for key, noun in [('name',r'姓名|名字'),('student_number',r'学号|学生编号')]:
        present=False
        for clause in re.split(r'[，,。；;\n]',text):
            if not re.search(noun,clause) or re.search(r'是否|有没有',clause):continue
            if re.search(r'没有|没印|没写|不带|不含',clause):present=False
            elif re.search(r'有|印|写|带|包含',clause):present=True
        if present:markers.append(key)
    return markers


def identity_description(markers):
    labels=[label for key,label in [('name','姓名'),('student_number','学号')] if key in markers]
    return '卡面印有'+'、'.join(labels)+'信息。' if labels else ''
