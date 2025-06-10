import streamlit as st
import io
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

def process_svg(svg_bytes, min_length_mm, target_dimension_mm, stroke_width_mm):
    ET.register_namespace('', "http://www.w3.org/2000/svg")
    tree = ET.parse(io.BytesIO(svg_bytes))
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

# Streamlit UI
st.title("SVG Path Cleaner (Streamlit Edition)")

uploaded_file = st.file_uploader("Upload SVG File", type="svg")
min_length_mm = st.number_input("Minimum Path Length to Keep (mm):", min_value=0.1, max_value=100.0, value=2.0, step=0.5)
dimension_mm = st.number_input("Scale Vector to Fit Dimension (mm):", min_value=1.0, max_value=1000.0, value=100.0, step=1.0)
stroke_width_mm = st.number_input("Final Stroke Width (mm):", min_value=0.1, max_value=10.0, value=1.5, step=0.5)

export_name = st.text_input("Export File Name (without .svg):", "")

if uploaded_file is not None:
    svg_bytes = uploaded_file.read()
    if st.button("Process SVG"):
        try:
            tree, original_count, kept_count = process_svg(
                svg_bytes,
                min_length_mm,
                dimension_mm,
                stroke_width_mm
            )
            st.success(f"Original paths: {original_count}")
            st.success(f"Remaining paths: {kept_count}")

            # Prepare output
            out = io.BytesIO()
            tree.write(out, encoding="utf-8", xml_declaration=True)
            out.seek(0)
            output_filename = (export_name.strip() or uploaded_file.name.replace('.svg', '_Clean')) + '.svg'
            st.download_button(
                label="Download Cleaned SVG",
                data=out,
                file_name=output_filename,
                mime="image/svg+xml"
            )
        except Exception as e:
            st.error(f"Error processing SVG: {e}")