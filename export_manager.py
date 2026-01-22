"""
导出管理器

支持将重复文件扫描结果导出为多种格式。
"""
import csv
import json
from datetime import datetime
from typing import List
from pathlib import Path
from dataclasses import asdict

from duplicate_finder import DuplicateGroup
from logger import get_logger
from utils import format_size  # 导入工具函数


class ExportManager:
    """导出管理器"""

    def __init__(self):
        self.log = get_logger()

    def export_to_csv(self, duplicate_groups: List[DuplicateGroup], output_path: str, include_metadata: bool = True) -> bool:
        """
        导出为 CSV 格式

        Args:
            duplicate_groups: 重复文件组列表
            output_path: 输出文件路径
            include_metadata: 是否包含元数据

        Returns:
            是否成功
        """
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                if include_metadata:
                    writer.writerow([
                        '哈希值', '文件大小', '组内文件数', '文件路径',
                        '文件名', '修改时间', '浪费空间'
                    ])
                else:
                    writer.writerow(['哈希值', '文件路径', '文件大小'])

                # Write data
                for group in duplicate_groups:
                    wasted_space = group.total_size - group.files[0].size
                    for i, file_info in enumerate(group.files):
                        if include_metadata:
                            writer.writerow([
                                group.hash_value,
                                file_info.size,
                                len(group.files),
                                file_info.path,
                                Path(file_info.path).name,
                                datetime.fromtimestamp(file_info.mtime).isoformat(),
                                wasted_space if i == 0 else ''
                            ])
                        else:
                            writer.writerow([
                                group.hash_value,
                                file_info.path,
                                file_info.size
                            ])

            self.log.info(f"成功导出 CSV 到: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"导出 CSV 失败: {e}")
            return False

    def export_to_json(self, duplicate_groups: List[DuplicateGroup], output_path: str, include_metadata: bool = True) -> bool:
        """
        导出为 JSON 格式

        Args:
            duplicate_groups: 重复文件组列表
            output_path: 输出文件路径
            include_metadata: 是否包含元数据

        Returns:
            是否成功
        """
        try:
            data = {
                'export_time': datetime.now().isoformat(),
                'total_groups': len(duplicate_groups),
                'total_files': sum(len(g.files) for g in duplicate_groups),
                'groups': []
            }

            for group in duplicate_groups:
                group_data = {
                    'hash': group.hash_value,
                    'file_count': len(group.files),
                    'total_size': group.total_size,
                    'wasted_space': group.total_size - group.files[0].size,
                    'files': []
                }

                for file_info in group.files:
                    file_data = {
                        'path': file_info.path,
                        'size': file_info.size
                    }

                    if include_metadata:
                        file_data.update({
                            'name': Path(file_info.path).name,
                            'directory': str(Path(file_info.path).parent),
                            'modified_time': datetime.fromtimestamp(file_info.mtime).isoformat()
                        })

                    group_data['files'].append(file_data)

                data['groups'].append(group_data)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.log.info(f"成功导出 JSON 到: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"导出 JSON 失败: {e}")
            return False

    def export_to_html(self, duplicate_groups: List[DuplicateGroup], output_path: str) -> bool:
        """
        导出为 HTML 报告

        Args:
            duplicate_groups: 重复文件组列表
            output_path: 输出文件路径

        Returns:
            是否成功
        """
        try:
            # Calculate statistics
            total_groups = len(duplicate_groups)
            total_files = sum(len(g.files) for g in duplicate_groups)
            total_wasted = sum(g.total_size - g.files[0].size for g in duplicate_groups)

            html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>重复文件扫描报告</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .stat-label {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .group {{
            margin: 20px 0;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
        }}
        .group-header {{
            background-color: #f8f9fa;
            padding: 15px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .group-header:hover {{
            background-color: #e9ecef;
        }}
        .group-title {{
            font-weight: bold;
            color: #495057;
        }}
        .group-info {{
            color: #6c757d;
            font-size: 14px;
        }}
        .file-list {{
            display: none;
        }}
        .file-list.show {{
            display: block;
        }}
        .file-item {{
            padding: 12px 15px;
            border-top: 1px solid #e0e0e0;
            display: flex;
            align-items: center;
        }}
        .file-item:hover {{
            background-color: #f8f9fa;
        }}
        .file-icon {{
            margin-right: 10px;
            color: #007bff;
        }}
        .file-info {{
            flex: 1;
        }}
        .file-path {{
            font-family: monospace;
            color: #495057;
            word-break: break-all;
        }}
        .file-meta {{
            font-size: 12px;
            color: #6c757d;
            margin-top: 4px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-primary {{
            background-color: #007bff;
            color: white;
        }}
        .badge-warning {{
            background-color: #ffc107;
            color: #212529;
        }}
        .timestamp {{
            text-align: center;
            color: #6c757d;
            font-size: 14px;
            margin-top: 30px;
        }}
        .progress-bar {{
            height: 8px;
            background-color: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 重复文件扫描报告</h1>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">重复文件组</div>
                <div class="stat-value">{total_groups}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">重复文件数</div>
                <div class="stat-value">{total_files}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">可释放空间</div>
                <div class="stat-value">{format_size(total_wasted)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">每组平均文件数</div>
                <div class="stat-value">{total_files / total_groups if total_groups > 0 else 0:.1f}</div>
            </div>
        </div>

        <div class="groups">
"""

            # Add each duplicate group
            for i, group in enumerate(duplicate_groups):
                wasted_space = group.total_size - group.files[0].size
                progress_percent = (wasted_space / group.total_size) * 100

                html_content += f"""
            <div class="group">
                <div class="group-header" onclick="toggleGroup({i})">
                    <div>
                        <span class="group-title">组 #{i + 1}</span>
                        <span class="badge badge-primary">{len(group.files)} 个文件</span>
                        <span class="badge badge-warning">浪费 {format_size(wasted_space)}</span>
                    </div>
                    <div class="group-info">
                        {format_size(group.total_size)} | {group.hash_value[:16]}...
                    </div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {progress_percent}%"></div>
                </div>
                <div class="file-list" id="group-{i}">
"""

                for file_info in group.files:
                    file_name = Path(file_info.path).name
                    file_dir = str(Path(file_info.path).parent)
                    modified_time = datetime.fromtimestamp(file_info.mtime).strftime("%Y-%m-%d %H:%M:%S")

                    html_content += f"""
                    <div class="file-item">
                        <div class="file-icon">📄</div>
                        <div class="file-info">
                            <div class="file-path">{file_name}</div>
                            <div class="file-meta">
                                📁 {file_dir} | 📊 {format_size(file_info.size)} | 🕒 {modified_time}
                            </div>
                        </div>
                    </div>
"""

                html_content += f"""
                </div>
            </div>
"""

            html_content += f"""
        </div>

        <div class="timestamp">
            报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>

    <script>
        function toggleGroup(index) {{
            const fileList = document.getElementById('group-' + index);
            fileList.classList.toggle('show');
        }}

        // Auto-expand first group
        document.addEventListener('DOMContentLoaded', function() {{
            const firstGroup = document.querySelector('.group-header');
            if (firstGroup) {{
                firstGroup.click();
            }}
        }});
    </script>
</body>
</html>
"""

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.log.info(f"成功导出 HTML 到: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"导出 HTML 失败: {e}")
            return False
