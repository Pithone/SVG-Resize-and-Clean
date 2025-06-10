import tkinter as tk
from tkinter import filedialog, messagebox
import os
import xml.etree.ElementTree as ET
from svgpathtools import parse_path
import re

def mm_to_px(mm, dpi=96):
    return (mm / 25.4) * dpi

def px_to_mm(px, dpi=96):
    return (px / dpi) * 25.4

def get_path_length(path_d):
    try:
        path = parse_path(path_d)
        return path.length()
    except Exception:
        return 0

def scale_path_data(path_d, scale_factor):
    try:
        path = parse_path(path_d)
        scaled_path = path.scaled(scale_factor)
        return scaled_path.d()
    except Exception:
        return path_d

def extract_all_subpaths(root):
    all_subpaths = []
    for elem in list(root.iter()):
        if elem.tag.endswith('path') and 'd' in elem.attrib:
            full_d = elem.attrib['d']
            matches = list(re.finditer(r'(?=[Mm])', full_d))
            indices = [m.start() for m in matches] + [len(full_d)]
            for i in range(len(indices) - 1):
                segment = full_d[indices[i]:indices[i + 1]].strip()
                if segment:
                    new_elem = ET.Element(elem.tag, attrib=elem.attrib.copy())
                    new_elem.set('d', segment)
                    all_subpaths.append(new_elem)
            root.remove(elem)
    return all_subpaths

def fit_viewbox_to_paths(group):
    all_coords = []
    for elem in group.findall('.//{http://www.w3.org/2000/svg}path'):
        try:
            path = parse_path(elem.attrib['d'])
            for segment in path:
                all_coords.append((segment.start.real, segment.start.imag))
                all_coords.append((segment.end.real, segment.end.imag))
        except Exception:
            continue
    if not all_coords:
        return 0, 0, 0, 0
    xs, ys = zip(*all_coords)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    return min_x, min_y, width, height

def process_svg(file_path, min_length_mm, target_dimension_mm, stroke_width_mm):
    ET.register_namespace('', "http://www.w3.org/2000/svg")
    tree = ET.parse(file_path)
    root = tree.getroot()

    subpaths = extract_all_subpaths(root)
    if not subpaths:
        return tree, 0, 0

    all_coords = []
    for el in subpaths:
        path = parse_path(el.attrib['d'])
        for segment in path:
            all_coords.append((segment.start.real, segment.start.imag))
            all_coords.append((segment.end.real, segment.end.imag))
    xs, ys = zip(*all_coords)
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    max_dim = max(width, height)
    target_px = mm_to_px(target_dimension_mm)
    scale_factor = target_px / max_dim

    min_length_px = mm_to_px(min_length_mm)
    kept = []

    for el in subpaths:
        scaled_d = scale_path_data(el.attrib['d'], scale_factor)
        el.set('d', scaled_d)
        new_len = get_path_length(scaled_d)
        if new_len >= min_length_px:
            kept.append(el)

    group = ET.Element('{http://www.w3.org/2000/svg}g')
    for el in kept:
        el.attrib.pop('style', None)
        el.attrib.pop('stroke-width', None)
        el.set('stroke', 'rgb(120,68,33)')
        el.set('stroke-width', f'{stroke_width_mm}mm')
        el.set('stroke-linecap', 'round')
        el.set('stroke-linejoin', 'round')
        el.set('fill', 'none')
        group.append(el)

    # Remove all old path elements
    for elem in list(root.iter()):
        if elem.tag.endswith('path'):
            root.remove(elem)

    root.append(group)

    min_x, min_y, final_width, final_height = fit_viewbox_to_paths(group)
    root.attrib['viewBox'] = f"{min_x} {min_y} {final_width} {final_height}"
    root.attrib['width'] = f"{px_to_mm(final_width)}mm"
    root.attrib['height'] = f"{px_to_mm(final_height)}mm"

    return tree, len(subpaths), len(kept)

# GUI
def main():
    root = tk.Tk()
    root.title("SVG Path Cleaner")

    file_path_var = tk.StringVar()
    min_length_var = tk.DoubleVar(value=2.0)
    dimension_var = tk.DoubleVar(value=100.0)
    stroke_width_var = tk.DoubleVar(value=1.5)
    original_count_var = tk.StringVar(value="Original paths: 0")
    remaining_count_var = tk.StringVar(value="Remaining paths: 0")
    export_name_var = tk.StringVar(value="")

    state = {'tree': None, 'original_svg_path': ''}

    def select_file():
        path = filedialog.askopenfilename(filetypes=[("SVG Files", "*.svg")])
        if path:
            file_path_var.set(path)
            export_name_var.set(os.path.splitext(os.path.basename(path))[0] + "_Clean")
            state['original_svg_path'] = path
            try:
                tree, original, remaining = process_svg(
                    path,
                    min_length_var.get(),
                    dimension_var.get(),
                    stroke_width_var.get()
                )
                state['tree'] = tree
                original_count_var.set(f"Original paths: {original}")
                remaining_count_var.set(f"Remaining paths: {remaining}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def process_again():
        path = file_path_var.get()
        if not path:
            messagebox.showerror("Error", "No SVG file selected.")
            return
        try:
            tree, original, remaining = process_svg(
                path,
                min_length_var.get(),
                dimension_var.get(),
                stroke_width_var.get()
            )
            state['tree'] = tree
            original_count_var.set(f"Original paths: {original}")
            remaining_count_var.set(f"Remaining paths: {remaining}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_file():
        if not state['tree'] or not state['original_svg_path']:
            messagebox.showerror("Error", "No file processed.")
            return

        dir_path = os.path.dirname(state['original_svg_path'])
        filename = export_name_var.get().strip() or "Cleaned_File"
        if not filename.lower().endswith(".svg"):
            filename += ".svg"
        export_path = os.path.join(dir_path, filename)

        state['tree'].write(export_path, encoding="utf-8", xml_declaration=True)
        messagebox.showinfo("Exported", f"File saved to:\n{export_path}")

    tk.Button(root, text="Select SVG File", command=select_file).pack(pady=5)
    tk.Entry(root, textvariable=file_path_var, width=60).pack(pady=2)

    tk.Label(root, text="Minimum Path Length to Keep (mm):").pack()
    tk.Spinbox(root, from_=0.1, to=100.0, increment=0.5, textvariable=min_length_var).pack()

    tk.Label(root, text="Scale Vector to Fit Dimension (mm):").pack()
    tk.Spinbox(root, from_=1, to=1000, increment=1, textvariable=dimension_var).pack()

    tk.Label(root, text="Final Stroke Width (mm):").pack()
    tk.Spinbox(root, from_=1.0, to=3.0, increment=0.5, textvariable=stroke_width_var).pack()

    tk.Label(root, textvariable=original_count_var).pack()
    tk.Label(root, textvariable=remaining_count_var).pack()

    tk.Button(root, text="Process", command=process_again).pack(pady=10)

    tk.Label(root, text="Export File Name:").pack()
    tk.Entry(root, textvariable=export_name_var, width=40).pack(pady=2)

    tk.Button(root, text="Export SVG", command=export_file).pack(pady=5)

    root.mainloop()

if __name__ == "__main__":
    main()
