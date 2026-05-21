"""
2026-02-24

韩家虎

修改内容：
    修改了CAD块分析工具类
    修改了切割轮廓检测工具类
    修改了主拆分函数
    添加运行时间统计

    修改实体文本提取流程、块和实体边界预计算，优化拆图时间

    将固定图框阈值升级为尺度自适应阈值（修改了筛选有效图框和去重方法）
    修改了块定义边界的嵌套块处理逻辑

    解决块参照附属信息误拆问题
    支持从子图多个加工说明中提取所有编号并生成多个文件
    修改厂内模号提取应用逻辑
"""
import os
import re
import warnings
import logging
import sys
from collections import defaultdict, Counter
from math import pi, radians, sqrt, cos, sin
from typing import Optional, List, Tuple, Dict

warnings.filterwarnings("ignore")

# 过滤ezdxf的DIMASSOC警告
logging.getLogger('ezdxf').setLevel(logging.ERROR)

# 重定向标准错误输出，过滤DIMASSOC警告
class DIMASSOCEFilter:
    def __init__(self):
        self.original_stderr = sys.stderr

    def write(self, text):
        if text and 'DIMASSOC' not in text:
            self.original_stderr.write(text)

    def flush(self):
        self.original_stderr.flush()

# 应用过滤器
sys.stderr = DIMASSOCEFilter()

try:
    import ezdxf
    from ezdxf.addons import Importer
    EZDXF_AVAILABLE = True
except ImportError:
    print("警告: ezdxf 库未找到。CAD 2D处理功能将无法运行。")
    ezdxf = None
    Importer = None
    EZDXF_AVAILABLE = False

if EZDXF_AVAILABLE:
    # 子图编号与文件名提取工具类
    class ProfessionalDrawingNumberExtractor:
        """专业图纸编号提取器 + 子图文件名提取"""

        def __init__(self):
            # 用于命名子图文件的正则（按优先级）
            self.filename_patterns = [
                re.compile(r'编号\s*[：:]\s*(\S+)'),
                # re.compile(r'加工说明[:：][\s_（）()\u4e00-\u9fa5/|｜]*([A-Z]+[A-Z0-9]*(?:(?!--)-[A-Z0-9]+)*)'),
                re.compile(r'加工说明[:：].*?([A-Z](?:[A-Z0-9]|[-_](?=[A-Z0-9]))*)'),
                re.compile(r'加工说明.*?[:：]\s*([A-Z]\d-\d{2})'),]

            self.explicit_label_re = re.compile(r'编号\s*[：:]\s*(\S+)')
            self.primary_patterns = [
                r'PH-[A-Z0-9]+', r'DIE-[A-Z0-9]+', r'[A-Z]{1,2}[0-9]{1,3}-[A-Z]{1,2}',
                r'[A-Z]{1,2}[0-9]{2,3}', r'[A-Z]{2,4}-[0-9]{1,3}',
            ]
            self.secondary_patterns = [
                r'[A-Z]{2,4}[0-9]{1,2}', r'[A-Z]{2,4}', r'MA-?[A-Z0-9]*', r'[A-Z][0-9]',
            ]
            self.excluded_terms = {
                '图纸', '设计', '审核', '标准', '规格', '材料', '备注', '品名', '编号',
                '数量', '热处理', '加工说明', '修改', '尺寸', '所有', '全周', '已订购',
                'TITLE', 'DRAWING', 'DESIGN', 'SCALE', 'DATE', '制图', '日期',
                '单位', '比例', '共页', '第页', '版本', 'PCS', '深', '攻', '钻',
                '割', '铰', '倒角', '沉头', '背', '穿', '让位', '合销', '导套',
                '螺丝', '基准', '弹簧', '定位', '精铣', '慢丝', '线割', '垂直度',
                '位置度', '加工', '夹板', '入子', '连接块', '外形', '绿色', '虚线',
                '直身', '拼装', '零件', '模板', '精磨'
            }
            self.cad_annotations = {
                'M', 'M0','M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10',
                'G', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9',
                'L', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9','P','P1',
                'U',  'U2', 'U3', 'U4', 'U5', 'X', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8', 'X9',
                'K', 'K1', 'K2', 'K3', 'K4', 'K5', 'A', 'A1', 'A2', 'A3', 'A4', 'A5',
                'Q', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9'
            }

        def extract_region_filename_by_patterns(self, subdrawing_data: Dict):
            # 从区域文字中提取子图文件名
            # 返回类型：str（单个文件名）或 List[str]（多个文件名）
            texts = subdrawing_data.get('texts', []) or []
            bounds = subdrawing_data.get('bounds', {})

            def is_in_bounds(text):
                x, y = text.get('position', [0, 0])
                return (bounds.get('min_x', -float('inf')) <= x <= bounds.get('max_x', float('inf')) and
                        bounds.get('min_y', -float('inf')) <= y <= bounds.get('max_y', float('inf')))

            # 优先检查"编号"正则，匹配到第一个就返回
            for t in texts:
                c = (t.get('content') or '').strip()
                if not c or not is_in_bounds(t):
                    continue
                m = self.filename_patterns[0].search(c)
                if m and m.group(1):
                    return self.generate_safe_filename(self._clean_candidate_after_label(m.group(1)))

            # 检查"编号"标签的后续文本
            for i, t in enumerate(texts):
                c = (t.get('content') or '').strip()
                if c in ('编号', '编号：', '编号:'):
                    for j in range(i + 1, min(i + 6, len(texts))):
                        nxt = (texts[j].get('content') or '').strip()
                        if nxt:
                            return self.generate_safe_filename(self._clean_candidate_after_label(nxt))

            # 收集所有"加工说明"的编号
            filenames = set()
            for t in texts:
                c = (t.get('content') or '').strip()
                if not c or not is_in_bounds(t):
                    continue
                for rx in self.filename_patterns[1:]:
                    m = rx.search(c)
                    if m and m.group(1):
                        candidate = self._clean_candidate_after_label(m.group(1))
                        if candidate:
                            filenames.add(self.generate_safe_filename(candidate))

            return list(filenames) if filenames else None

        def extract_drawing_number_from_region(self, subdrawing_data: Dict) -> Dict:
            # 从区域文字中提取图纸编号
            bounds = subdrawing_data['bounds']
            texts = subdrawing_data['texts']
            filtered_texts = self._preprocess_texts(texts)
            if not filtered_texts:
                return {'drawing_number': None, 'is_from_bottom_right': False}
            
            min_x, max_x = bounds['min_x'], bounds['max_x']
            min_y, max_y = bounds['min_y'], bounds['max_y']
            width = max_x - min_x
            height = max_y - min_y
            
            extraction_methods = [
                self._extract_from_explicit_labels,
                self._extract_from_key_positions,
                self._extract_from_pattern_matching
            ]
            
            for method in extraction_methods:
                result = method(bounds, filtered_texts)
                if result:
                    if self._validate_drawing_number(result):
                        is_from_bottom_right = self._is_from_bottom_right(result, bounds, filtered_texts)
                        return {'drawing_number': result, 'is_from_bottom_right': is_from_bottom_right}
            return {'drawing_number': None, 'is_from_bottom_right': False}

        def _preprocess_texts(self, texts: List) -> List:
            # 预处理区域文字，过滤无效内容
            content_frequency = Counter([text['content'].strip() for text in texts])
            processed = []
            for text in texts:
                content = text['content'].strip()
                if not content or len(content) > 30:
                    continue
                if any(term in content for term in self.excluded_terms):
                    continue
                if content in self.cad_annotations:
                    continue
                if len(content) <= 2 and content_frequency[content] > 5:
                    continue
                if self._is_dimension_or_value(content):
                    continue
                processed.append(text)
            return processed

        def _is_dimension_or_value(self, content: str) -> bool:
            # 判断文字是否为尺寸或数值
            dimension_patterns = [
                r'^\d+\.?\d*$', r'^\d+\.?\d*[LWTHDRC]$', r'^Φ\d+\.?\d*$', r'^R\d+\.?\d*$',
                r'^\d+\.?\d*°$', r'^\d+\.?\d*mm$', r'^M\d+x\d+\.?\d*$', r'^\d+\.?\d*深$',
                r'^C\d+\.?\d*$', r'^HRC\d+-\d+$', r'^\d+\.?\d*[×xX]\d+\.?\d*',
            ]
            return any(re.match(pattern, content) for pattern in dimension_patterns)

        def _extract_from_explicit_labels(self, bounds: Dict, texts: List) -> Optional[str]:
            # 从显式标签提取编号
            for t in texts:
                m = self.explicit_label_re.search(t['content'].strip())
                if m:
                    cand = self._clean_candidate_after_label(m.group(1))
                    if self._validate_drawing_number(cand):
                        return cand
            for i, t in enumerate(texts):
                c = t['content'].strip()
                if c in ('编号', '编号：', '编号:'):
                    for j in range(i + 1, min(i + 6, len(texts))):
                        cand = self._clean_candidate_after_label(texts[j]['content'].strip())
                        if self._validate_drawing_number(cand):
                            return cand
            return None

        def _extract_from_processing_instruction_with_number(self, texts: List) -> Optional[str]:
            """从加工说明中提取数字或大写字母开头的编号"""
            pattern = re.compile(r'加工说明[:：][\s_（）()\u4e00-\u9fa5/|｜]*([A-Z0-9]+[A-Z0-9]*(?:(?!--)-[A-Z0-9]+)*)')
            
            for text in texts:
                content = text['content'].strip()
                match = pattern.search(content)
                if match:
                    candidate = match.group(1)
                    if re.match(r'^[A-Z0-9][A-Za-z0-9-]*$', candidate):
                        return candidate
            return None

        def _is_from_bottom_right(self, content: str, bounds: Dict, texts: List) -> bool:
            """判断文本是否来自右下角区域"""
            min_x, max_x = bounds['min_x'], bounds['max_x']
            min_y, max_y = bounds['min_y'], bounds['max_y']
            width = max_x - min_x
            height = max_y - min_y
            
            right_bottom_x = max_x - width * 0.2
            right_bottom_y = min_y + height * 0.2
            
            for text in texts:
                if text['content'].strip() == content:
                    x, y = text['position']
                    if x >= right_bottom_x and y <= right_bottom_y:
                        return True
            return False

        def _clean_candidate_after_label(self, s: str) -> str:
            # 清理标签后的编号候选
            cleaned = (s or '').strip()
            if not cleaned:
                return cleaned
            cleaned = cleaned.split()[0]
            cleaned = cleaned.strip('，,。.;；:：)]】）\'"').strip('([【（\'"')
            cleaned = re.sub(r'^[\s\-_]+|[\s\-_]+$', '', cleaned)
            return cleaned[:64] if len(cleaned) > 64 else cleaned

        def _extract_from_key_positions(self, bounds: Dict, texts: List) -> Optional[str]:
            # 从关键位置提取编号
            position_zones = [
                {'name': 'top_left', 'bounds': self._define_zone_bounds(bounds, 0, 0.35, 0.7, 1.0), 'weight': 2.5},
                {'name': 'title_block', 'bounds': self._define_zone_bounds(bounds, 0.7, 1.0, 0, 0.25), 'weight': 2.0},
                {'name': 'top_right','bounds': self._define_zone_bounds(bounds,  0.65, 1.0, 0.75,1.0),'weight': 1.5 },
                {'name': 'bottom_left', 'bounds': self._define_zone_bounds(bounds, 0, 0.35, 0, 0.25), 'weight': 1.8},
            ]
            best_candidate, best_score = None, 0.0
            for zone in position_zones:
                for text in self._get_texts_in_bounds(texts, zone['bounds']):
                    quality = self._calculate_quality_score(text['content'].strip())
                    if quality > 0:
                        score = quality * zone['weight']
                        if score > best_score:
                            best_score, best_candidate = score, text['content'].strip()
            return best_candidate if best_score > 2.0 else None

        def _extract_from_pattern_matching(self, bounds: Dict, texts: List) -> Optional[str]:
            # 从模式匹配提取编号
            candidates = []
            pattern_groups = [
                (self.primary_patterns, 3.0),
                (self.secondary_patterns, 2.0),
            ]
            for text in texts:
                content = text['content'].strip()
                for patterns, base_w in pattern_groups:
                    for pat in patterns:
                        if re.match(pat + '$', content):
                            pos_w = self._calculate_position_weight(text['position'], bounds)
                            candidates.append((content, base_w * pos_w))
                            break
            if candidates:
                return max(candidates, key=lambda x: x[1])[0]
            return None

        def _validate_drawing_number(self, content: str) -> bool:
            # 校验提取到的编号是否合法
            if not content or len(content) > 16:
                return False
            invalid_patterns = [
                r'^[:：].*', r'.*[:：]\s*$', r'^\d+\.\d+$', r'^[0-9]{4,}$',
                r'.*说明.*', r'.*加工.*', r'.*深$', r'.*磨$', r'^[\d\.\-\+\s]+$',
                r'.*PCS.*',
            ]
            if any(re.match(p, content) for p in invalid_patterns):
                return False
            valid_patterns = [
                r'^[A-Z]{1,4}[0-9]*$',
                r'^[A-Z]+-[A-Z0-9]+$',
                r'^[A-Z]+[0-9]*-[0-9]+$',  # 匹配大写字母开头+n个数字+短横线+1个或多个数字
                r'^[A-Z]{2,4}$',
            ]
            return any(re.match(p, content) for p in valid_patterns)

        def _calculate_quality_score(self, content: str) -> float:
            # 计算编号内容的质量分数
            if not content:
                return 0.0
            score = 0.0
            n = len(content)
            if 2 <= n <= 6:
                score += 3.0
            elif n == 1:
                score += 0.5
            else:
                score += 1.0
            if re.match(r'^[A-Z]+-[A-Z0-9]+$', content):
                score += 4.0
            elif re.match(r'^[A-Z]{1,3}[0-9]{1,3}$', content):
                score += 3.5
            elif re.match(r'^[A-Z]{2,4}$', content):
                score += 2.5
            elif re.match(r'^[A-Z][0-9]$', content):
                score += 2.0
            if re.search(r'[0-9]', content):
                score += 1.0
            if content in self.cad_annotations:
                score = 0.0
            return score

        def _calculate_position_weight(self, position: Tuple, bounds: Dict) -> float:
            # 计算编号在区域中的位置权重
            x, y = position
            width, height = bounds['width'], bounds['height']
            xn = (x - bounds['min_x']) / width
            yn = (y - bounds['min_y']) / height
            x_w = 1.2 - xn * 0.4
            y_w = 1.0 if yn > 0.75 else (0.9 if yn < 0.25 else 0.4)
            return x_w * y_w

        def _define_zone_bounds(self, bounds: Dict, x_start: float, x_end: float,
                                y_start: float, y_end: float) -> Dict:
            # 定义区域边界
            w, h = bounds['width'], bounds['height']
            return {
                'min_x': bounds['min_x'] + w * x_start,
                'max_x': bounds['min_x'] + w * x_end,
                'min_y': bounds['min_y'] + h * y_start,
                'max_y': bounds['min_y'] + h * y_end,
            }

        def _get_texts_in_bounds(self, texts: List, zone_bounds: Dict) -> List:
            # 获取区域内的文字
            return [t for t in texts
                    if (zone_bounds['min_x'] <= t['position'][0] <= zone_bounds['max_x'] and
                            zone_bounds['min_y'] <= t['position'][1] <= zone_bounds['max_y'])]

        def generate_safe_filename(self, name: str) -> str:
            # 生成安全的文件名
            if not name:
                return "未知编号"
            s = re.sub(r'[<>:"/\\|?*]', '_', name.strip()).replace(' ', '_')
            s = s.rstrip(' .')
            return s if len(s) <= 80 else s[:80]

    # 文字实体过滤与处理工具
    class IntelligentTextProcessor:
        """智能文字处理器"""

        def __init__(self):
            self.noise_patterns = [
                r'^\d+\.?\d*$', r'^[\d\.\-\+\s]+$', r'^\d+\.?\d*[LWTHDRC]$',
                r'^Φ\d+\.?\d*', r'^R\d+\.?\d*', r'^M\d+x',
                r'^\d+\.?\d*°$', r'^\d+\.?\d*mm$', r'^\d+\.?\d*[×xX]\d+\.?\d*',
                r'.*深$', r'.*攻$', r'.*钻$',
            ]
            self.meaningful_keywords = [
                '品名', '编号', '材料', '热处理', '数量',
                '加工说明', '尺寸', '修改', '备注', '规格', '型号'
            ]

        def process_text_list(self, texts: List[Dict]) -> List[Dict]:
            # 过滤并处理文字实体，去除无用信息
            if not texts:
                return []
            counter = Counter([t['content'].strip() for t in texts])
            processed = []
            for t in texts:
                c = t['content'].strip()
                if self._should_keep_text(c, counter):
                    processed.append(t)
            return processed

        def _should_keep_text(self, content: str, counter: Counter) -> bool:
            # 判断文字是否应保留
            if not content:
                return False
            if len(content) > 50:
                return False
            if any(k in content for k in self.meaningful_keywords):
                return True
            if any(re.match(p, content) for p in self.noise_patterns):
                return False
            if len(content) <= 3 and counter[content] > 8:
                return False
            if len(content) <= 1 and counter[content] > 3:
                return False
            return True

    # CAD块分析与拆分工具
    class OptimizedCADBlockAnalyzer:
        """优化的CAD块分析器 + 修复BlockLayout错误 + 添加拆分条件筛选"""

        def __init__(self):
            """初始化分析器，创建文本处理器、编号提取器和切割检测器实例"""
            self.all_texts = []
            self.all_entities = []
            self.frame_blocks = []
            self.sub_drawings = {}
            self.layer_colors = {}
            self.text_processor = IntelligentTextProcessor()
            self.number_extractor = ProfessionalDrawingNumberExtractor()
            self.cutting_detector = StrictCuttingDetector()
            self.doc = None
            self.msp = None
            self.classify_map = None
            self.common_factory_model_number = None

            # 拆分条件配置（已去除关键词过滤，所有图框均拆分）
            self.required_keywords = []
            self.excluded_keywords = []

            # 块边界缓存：{block_name: local_bounds}
            self._block_local_bounds_cache = {}
            # 块内实体边界缓存：{entity_handle: local_bounds}，性能优化
            self._block_entity_bounds_cache = {}

        def analyze_cad_file(self, file_path: str) -> Dict:
            # CAD文件详细分析，提取图层、文字、实体、图框块，识别子图区域
            print(f"开始放宽分析CAD文件: {file_path}")
            try:
                doc = ezdxf.readfile(file_path)
                msp = doc.modelspace()
                self.doc = doc
                self.msp = msp

                self._extract_layer_colors(doc)
                self._extract_all_entities_and_texts(msp)  # 优化：一次遍历同时提取文字和几何实体
                self._identify_frame_blocks(msp)
                self._precalculate_all_block_bounds(doc)  # 性能优化：预计算所有块定义边界
                self._create_subdrawing_regions()
                self._assign_texts_to_regions()
                self._extract_factory_model_number_from_regions()
                self._analyze_cutting_contours_for_regions()

                print(f"放宽分析完成，识别出 {len(self.sub_drawings)} 个满足条件的子图区域")
                return self.sub_drawings
            except Exception as e:
                print(f"文件分析失败: {str(e)}")
                import traceback
                traceback.print_exc()
                return {}

        def _should_process_region(self, region_data: Dict) -> bool:
            """检查区域是否满足拆分条件（关键词为空时跳过检查，全部通过）"""
            texts = region_data.get('texts', [])
            text_contents = [t.get('content', '') for t in texts]

            # 必须包含关键词检查（列表为空时跳过）
            if self.required_keywords:
                has_required = any(any(keyword in content for keyword in self.required_keywords)
                                   for content in text_contents)
                if not has_required:
                    return False

            # 排除关键词检查（列表为空时跳过）
            if self.excluded_keywords:
                has_excluded = any(any(keyword in content for keyword in self.excluded_keywords)
                                   for content in text_contents)
                if has_excluded:
                    return False

            return True

        def _safe_spline_points(self, entity):
            # 安全提取样条点
            pts = []
            try:
                if hasattr(entity, 'control_points') and entity.control_points:
                    for p in entity.control_points:
                        try:
                            pts.append((float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0))
                        except Exception:
                            pts.append((float(p.x), float(p.y), float(getattr(p, 'z', 0.0))))
                if not pts and hasattr(entity, 'fit_points') and entity.fit_points:
                    for p in entity.fit_points:
                        pts.append((float(p.x), float(p.y), float(getattr(p, 'z', 0.0))))
                if not pts and hasattr(entity, 'vertices'):
                    for v in entity.vertices:
                        if hasattr(v, 'dxf') and hasattr(v.dxf, 'location'):
                            pts.append((float(v.dxf.location.x), float(v.dxf.location.y),
                                        float(getattr(v.dxf.location, 'z', 0.0))))
                if not pts and hasattr(entity.dxf, 'start_point') and hasattr(entity.dxf, 'end_point'):
                    s = entity.dxf.start_point
                    e = entity.dxf.end_point
                    pts = [(float(s.x), float(s.y), float(getattr(s, 'z', 0.0))),
                           (float(e.x), float(e.y), float(getattr(e, 'z', 0.0)))]
            except Exception:
                pass
            return pts

        def _point_in_bounds(self, pt, bounds: Dict) -> bool:
            # 判断点是否在区域内
            if pt is None:
                return False
            x, y = pt
            return (bounds['min_x'] <= x <= bounds['max_x']) and (bounds['min_y'] <= y <= bounds['max_y'])

        def _ellipse_start_end_points(self, entity) -> Tuple[
            Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
            # 获取椭圆起止点
            try:
                tool = entity.construction_tool()
                sp = (float(tool.start_point.x), float(tool.start_point.y))
                ep = (float(tool.end_point.x), float(tool.end_point.y))
                return sp, ep
            except Exception:
                pass

            try:
                c = entity.dxf.center
                maj = entity.dxf.major_axis
                ratio = float(getattr(entity.dxf, 'ratio', 0.5) or 0.5)
                a_x, a_y = float(maj.x), float(maj.y)
                b_x, b_y = -a_y * ratio, a_x * ratio

                t0 = float(getattr(entity.dxf, 'start_param', 0.0) or 0.0)
                t1 = float(getattr(entity.dxf, 'end_param', 2 * pi) or 2 * pi)

                cx, cy = float(c.x), float(c.y)

                def eval_point(t):
                    return (cx + a_x * cos(t) + b_x * sin(t),
                            cy + a_y * cos(t) + b_y * sin(t))

                sp = eval_point(t0)
                ep = eval_point(t1)
                return sp, ep
            except Exception:
                return None, None

        def _ellipse_hits_region_by_endpoints(self, entity, bounds: Dict) -> bool:
            # 判断椭圆端点是否在区域内
            sp, ep = self._ellipse_start_end_points(entity)
            return self._point_in_bounds(sp, bounds) or self._point_in_bounds(ep, bounds)

        def _get_entity_bounds_optimized(self, e) -> Optional[Dict]:
            """
            优化的实体边界计算方法 - 提取为类方法以供复用
            """
            try:
                entity_type = e.dxftype()
                bounds = None
                # ====== 直线 ======
                if entity_type == 'LINE':
                    start = e.dxf.start
                    end = e.dxf.end
                    bounds = {'min_x': min(start.x, end.x), 'max_x': max(start.x, end.x),
                              'min_y': min(start.y, end.y), 'max_y': max(start.y, end.y),
                              'start': (start.x, start.y), 'end': (end.x, end.y)}
                # ====== 圆 ======
                elif entity_type == 'CIRCLE':
                    center = e.dxf.center
                    radius = e.dxf.radius
                    bounds = {'min_x': center.x - radius, 'max_x': center.x + radius,
                              'min_y': center.y - radius, 'max_y': center.y + radius}
                # ====== 圆弧 ======
                elif entity_type == 'ARC':
                    center = e.dxf.center
                    radius = e.dxf.radius
                    start_angle = e.dxf.start_angle
                    end_angle = e.dxf.end_angle
                    angles = [start_angle, end_angle]
                    for a in [0, 90, 180, 270]:
                        if start_angle < end_angle:
                            if start_angle <= a <= end_angle:
                                angles.append(a)
                        else:
                            if a >= start_angle or a <= end_angle:
                                angles.append(a)
                    pts = []
                    for ang in angles:
                        rad = radians(ang)
                        x = center.x + radius * cos(rad)
                        y = center.y + radius * sin(rad)
                        pts.append((x, y))
                    xs, ys = zip(*pts)
                    bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}
                # ====== 多段线 ======
                elif entity_type in ('LWPOLYLINE', 'POLYLINE'):
                    pts = self._get_polyline_points(e)
                    if pts:
                        xs, ys = zip(*pts)
                        bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}
                # ====== 椭圆 ======
                elif entity_type == 'ELLIPSE':
                    center = e.dxf.center
                    major_axis = e.dxf.major_axis
                    ratio = float(getattr(e.dxf, 'ratio', 0.5) or 0.5)
                    bounds = {'min_x': center.x - major_axis.x, 'max_x': center.x + major_axis.x,
                              'min_y': center.y - (major_axis.y * ratio), 'max_y': center.y + (major_axis.y * ratio)}
                # ====== 文字类实体 ======
                elif entity_type in ('TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF', 'LEADER', 'TABLE'):
                    pos = getattr(e.dxf, 'insert', None) or getattr(e.dxf, 'pos', None)
                    if pos:
                        height = float(getattr(e.dxf, 'height', 2.5) or 2.5)
                        width = height * 5
                        bounds = {'min_x': pos.x - width / 2, 'max_x': pos.x + width / 2,
                                  'min_y': pos.y - height / 2, 'max_y': pos.y + height / 2}
                # ====== 标注 ======
                elif entity_type == 'DIMENSION':
                    defpoint = e.dxf.defpoint
                    textpoint = e.dxf.text_midpoint or e.dxf.text_location
                    text_height = float(getattr(e.dxf, 'text_height', 2.5))
                    text_width = text_height * 2
                    min_x = textpoint.x - text_width / 2
                    max_x = textpoint.x + text_width / 2
                    min_y = textpoint.y - text_height / 2
                    max_y = textpoint.y + text_height / 2
                    min_x = min(min_x, defpoint.x)
                    max_x = max(max_x, defpoint.x)
                    min_y = min(min_y, defpoint.y)
                    max_y = max(max_y, defpoint.y)
                    bounds = {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}

                # ====== 块引用 ======
                elif entity_type == 'INSERT':
                    block_def = e.doc.blocks.get(e.dxf.name)
                    if block_def:
                        bounds = self._calculate_block_bounds(block_def, e)

                # ====== 样条曲线 ======
                elif entity_type == 'SPLINE':
                    pts = self._safe_spline_points(e)
                    if pts:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        buffer = 1.0
                        bounds = {'min_x': min(xs) - buffer, 'max_x': max(xs) + buffer,
                                  'min_y': min(ys) - buffer, 'max_y': max(ys) + buffer}

                return bounds

            except Exception:
                return None

        def export_regions_to_dxf(self, output_dir: str):
            # 导出所有满足条件的子图为独立DXF文件
            if not self.doc or not self.msp:
                print("导出失败：未加载文档。")
                return
            os.makedirs(output_dir, exist_ok=True)
            all_msp_entities = list(self.msp)

            doc_units = self.doc.units
            print(f"源文件单位类型: {doc_units} (0=无单位, 1=英寸, 3=毫米, 4=厘米)")
            unit_to_mm = {
                0: 1.0, 1: 25.4, 2: 304.8, 3: 1.0, 4: 10.0, 5: 1000.0,
            }
            scale = unit_to_mm.get(doc_units, 1.0)
            print(f"单位转换因子（转为毫米）: {scale}")

            # ====== 性能优化：预先计算所有实体边界并缓存 ======
            print(f"正在预计算 {len(all_msp_entities)} 个实体的边界...")
            entity_bounds_cache = {}
            entity_types_cache = {}
            for e in all_msp_entities:
                try:
                    handle = e.dxf.handle
                    entity_types_cache[handle] = e.dxftype()
                    # 预计算边界
                    entity_bounds_cache[handle] = self._get_entity_bounds_optimized(e)
                except Exception:
                    continue
            print(f"边界预计算完成，成功缓存 {len(entity_bounds_cache)} 个实体")
            # ==================================================

            def is_entity_in_region(ent_bounds: Dict, region_bounds: Dict, entity_type: str = None) -> bool:
                """判断实体是否在指定区域内（INSERT和LINE有特殊判断逻辑）"""
                center_x = (ent_bounds['min_x'] + ent_bounds['max_x']) / 2
                center_y = (ent_bounds['min_y'] + ent_bounds['max_y']) / 2

                if entity_type == 'INSERT':
                    # 块引用：只需判断插入点（中心点）是否在区域内
                    return (region_bounds['min_x'] <= center_x <= region_bounds['max_x'] and
                            region_bounds['min_y'] <= center_y <= region_bounds['max_y'])

                elif entity_type == 'LINE':
                    # 直线：需要判断起点和终点都在区域内
                    sx, sy = ent_bounds['start']
                    ex, ey = ent_bounds['end']
                    return (region_bounds['min_x'] <= sx <= region_bounds['max_x'] and
                            region_bounds['min_y'] <= sy <= region_bounds['max_y'] and
                            region_bounds['min_x'] <= ex <= region_bounds['max_x'] and
                            region_bounds['min_y'] <= ey <= region_bounds['max_y'])

                else:
                    # 其他实体：判断中心点是否在区域内
                    return (region_bounds['min_x'] <= center_x <= region_bounds['max_x'] and
                            region_bounds['min_y'] <= center_y <= region_bounds['max_y'])

            export_count = 0
            for idx, (region_id, region) in enumerate(self.sub_drawings.items(), start=1):
                bounds = region['bounds']

                # 打印当前子图信息
                block_name = region.get('frame_block', {}).get('block_name', '未知')
                region_width = bounds['max_x'] - bounds['min_x']
                region_height = bounds['max_y'] - bounds['min_y']
                region_area = region_width * region_height
                print(f"\n[子图 {idx}/{len(self.sub_drawings)}] ID: {region_id}")
                print(f"  图框块: {block_name}")
                print(f"  区域尺寸: {region_width:.1f} × {region_height:.1f}")
                print(f"  区域面积: {region_area:.0f}")

                # 关键修复：不要对region bounds乘scale，因为ent_bounds也没有乘scale
                # 所有bounds都应该在原始DXF坐标系下比较
                region_bounds = {
                    'min_x': bounds['min_x'],
                    'max_x': bounds['max_x'],
                    'min_y': bounds['min_y'],
                    'max_y': bounds['max_y']
                }

                # 计算纵向分割阈值：子图底部16%区域为非主体区域
                region_height = region_bounds['max_y'] - region_bounds['min_y']
                vertical_threshold = region_bounds['min_y'] + region_height * 0.16

                # 获取当前区域图框块的INSERT实体(用于精确过滤)
                current_frame_insert = region['frame_block'].get('insert_entity')
                current_frame_handle = current_frame_insert.dxf.handle if current_frame_insert else None

                # 获取厂内模号文本实体的handle（用于过滤）
                factory_model_handle = region.get('factory_model_handle')

                selected_entities = []

                for e in all_msp_entities:
                    try:
                        handle = e.dxf.handle

                        # 过滤厂内模号文本实体
                        if factory_model_handle and handle == factory_model_handle:
                            continue

                        # 使用handle精确匹配当前区域的图框块,避免误伤同名内部块
                        entity_type = entity_types_cache.get(handle)  # 使用缓存的类型
                        if entity_type == 'INSERT' and current_frame_handle:
                            if handle == current_frame_handle:
                                continue

                        ent_bounds = entity_bounds_cache.get(handle)  # 使用缓存的边界
                        if not ent_bounds:
                            continue

                        # 纵向位置过滤：底部16%区域的实体不纳入子图输出
                        # 判断实体中心点是否在底部区域内（包含分割线）
                        entity_center_y = (ent_bounds['min_y'] + ent_bounds['max_y']) / 2
                        if entity_center_y <= vertical_threshold:
                            continue

                        if is_entity_in_region(ent_bounds, region_bounds, entity_type):
                            selected_entities.append(e)

                    except Exception as ex:
                        print(f"筛选实体 {e.dxftype()} 时出错: {str(ex)}")
                        continue

                if not selected_entities:
                    print(f"[导出提示] {region_id} 内未找到可导出的实体，跳过。")
                    continue
                
                # 复制文字样式和标注样式
                new_doc = ezdxf.new(dxfversion=self.doc.dxfversion)
                try:
                    new_doc.units = self.doc.units
                    
                    # 0. 先复制线型（标注样式可能引用线型）
                    for ltype in self.doc.linetypes:
                        ltype_name = ltype.dxf.name
                        if ltype_name not in new_doc.linetypes:
                            new_ltype = new_doc.linetypes.new(ltype_name)
                            try:
                                new_ltype.dxf.description = ltype.dxf.description
                            except Exception:
                                pass
                            try:
                                new_ltype.dxf.pattern = ltype.dxf.pattern
                            except Exception:
                                pass

                    # 1. 先复制文字样式（标注依赖文字样式）
                    for text_style in self.doc.styles:
                        style_name = text_style.dxf.name
                        if style_name not in new_doc.styles:
                            new_text_style = new_doc.styles.new(style_name)
                        else:
                            new_text_style = new_doc.styles.get(style_name)
                        
                        # 复制所有文字样式属性
                        attrs_to_copy = ['font', 'bigfont', 'height', 'width', 'oblique', 'flags', 'generation_flags']
                        for attr in attrs_to_copy:
                            try:
                                if hasattr(text_style.dxf, attr):
                                    setattr(new_text_style.dxf, attr, getattr(text_style.dxf, attr))
                            except Exception:
                                pass
                    
                    # 2. 再复制标注样式（完整复制所有属性）
                    for dim_style in self.doc.dimstyles:
                        style_name = dim_style.dxf.name
                        if style_name not in new_doc.dimstyles:
                            new_doc.dimstyles.new(style_name)
                        new_dim = new_doc.dimstyles.get(style_name)
                        
                        # 复制所有标注样式属性（关键：包含小数位数和零抑制）
                        dim_attrs_to_copy = [
                            # 文字相关
                            'dimtxsty', 'dimtxt', 'dimtad', 'dimgap', 'dimjust', 'dimtih', 'dimtoh',
                            # 数值格式（关键属性）
                            'dimdec', 'dimzin', 'dimlunit', 'dimdsep', 'dimrnd', 'dimtfac',
                            # 线条和箭头
                            'dimscale', 'dimasz', 'dimblk', 'dimblk1', 'dimblk2', 'dimdle', 'dimdli',
                            'dimexe', 'dimexo', 'dimclrd', 'dimclre', 'dimclrt',
                            # 单位和测量
                            'dimlfac', 'dimpost', 'dimapost', 'dimalt', 'dimaltd', 'dimaltf',
                            # 公差
                            'dimtol', 'dimlim', 'dimtp', 'dimtm', 'dimtolj',
                            # 其他
                            'dimse1', 'dimse2', 'dimtad', 'dimfrac', 'dimlwd', 'dimlwe'
                        ]
                        
                        for attr in dim_attrs_to_copy:
                            try:
                                if hasattr(dim_style.dxf, attr):
                                    setattr(new_dim.dxf, attr, getattr(dim_style.dxf, attr))
                            except Exception:
                                pass
                        
                        # 特别处理测量值（保留原始设置）
                        try:
                            if hasattr(dim_style, 'dxfattribs'):
                                for key, value in dim_style.dxfattribs().items():
                                    if key not in ['handle', 'owner']:
                                        try:
                                            setattr(new_dim.dxf, key, value)
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                            
                            # 显式保证小数点分隔符和小数位数与原图一致
                            try:
                                if hasattr(dim_style.dxf, 'dimdsep'):
                                    new_dim.dxf.dimdsep = dim_style.dxf.dimdsep
                                else:
                                    new_dim.dxf.dimdsep = '.'
                            except Exception:
                                new_dim.dxf.dimdsep = '.'
                            try:
                                if hasattr(dim_style.dxf, 'dimdec'):
                                    new_dim.dxf.dimdec = dim_style.dxf.dimdec
                            except Exception:
                                pass
                except Exception as e:
                    print(f"复制文字样式和标注样式时出错: {str(e)}")
                try:
                    for src_block in self.doc.blocks:
                        block_name = src_block.dxf.name
                        # 跳过模型空间和图纸空间
                        if block_name in ('*Model_Space', '*Paper_Space', '*Paper_Space0'):
                            continue
                        # 如果新文档中没有这个块，则创建
                        if block_name not in new_doc.blocks:
                            try:
                                new_block = new_doc.blocks.new(name=block_name)
                                # 复制块的属性
                                try:
                                    new_block.dxf.description = src_block.dxf.description
                                except Exception:
                                    pass
                                try:
                                    new_block.dxf.base_point = src_block.dxf.base_point
                                except Exception:
                                    pass
                            except Exception as e:
                                print(f"创建块 {block_name} 时出错: {e}")
                except Exception as e:
                    print(f"复制块定义时出错: {str(e)}")

                target_msp = new_doc.modelspace()
                importer = Importer(self.doc, new_doc)
                importer.import_entities(selected_entities, target_msp)
                importer.finalize()
                # 强制所有DIMENSION实体使用指定的dimstyle和dimtxsty
                force_dimstyle_name = None
                # 自动选择原图中第一个非Standard的dimstyle作为默认
                for ds in new_doc.dimstyles:
                    if ds.dxf.name != 'Standard':
                        force_dimstyle_name = ds.dxf.name
                        break
                if not force_dimstyle_name:
                    force_dimstyle_name = 'Standard'

                # 获取该dimstyle对应的dimtxsty
                force_dimtxsty = None
                try:
                    force_dimtxsty = new_doc.dimstyles.get(force_dimstyle_name).dxf.dimtxsty
                except Exception:
                    force_dimtxsty = 'Standard'

                for dim in target_msp.query('DIMENSION'):
                    try:
                        dim.dxf.dimstyle = force_dimstyle_name
                        # 强制dimtxsty（标注用文字样式）
                        if hasattr(dim.dxf, 'dimtxsty'):
                            dim.dxf.dimtxsty = force_dimtxsty
                        # 兼容部分CAD只认dimstyle里的dimtxsty
                        ds = new_doc.dimstyles.get(force_dimstyle_name)
                        if ds and hasattr(ds.dxf, 'dimtxsty'):
                            ds.dxf.dimtxsty = force_dimtxsty
                    except Exception as e:
                        print(f"修正DIMENSION样式失败: {e}")
                # 从源文档复制块的单位设置和缩放比例到新文档
                for block in new_doc.blocks:
                    block_name = block.dxf.name
                    if not isinstance(block_name, str):
                        print(f"跳过无效块名（非字符串类型）: {block_name}")
                        continue
                    src_block = self.doc.blocks.get(block_name)
                    if src_block and block:
                        try:
                            block.dxf.units = src_block.dxf.units
                        except Exception:
                            pass
                        try:
                            block.dxf.xscale = src_block.dxf.xscale
                            block.dxf.yscale = src_block.dxf.yscale
                            block.dxf.zscale = src_block.dxf.zscale
                        except Exception:
                            pass

                def normalize_name_internal(name: str) -> str:
                    """规范化名称用于内部存储和比较，保留原始下划线"""
                    if not name:
                        return name
                    # 只替换非法字符，保留字母、数字和下划线
                    name = re.sub(r'[^a-zA-Z0-9_]+', '_', name)
                    name = name.strip('_')
                    return name

                def sanitize_filename(name: str) -> str:
                    """清理文件名，移除非法字符，用于最终输出文件名时将下划线替换为短横线"""
                    if not name:
                        return name
                    # 先使用内部规范化
                    name = normalize_name_internal(name)
                    # 然后将下划线替换为短横线用于文件名输出
                    name = name.replace('_', '-')
                    name = name.strip('-')
                    return name

                # 提取区域文件名：优先使用正则模式提取，失败则使用图号提取
                fname_result = self.number_extractor.extract_region_filename_by_patterns(region)
                
                # 处理返回结果：可能是单个文件名（str）或多个文件名（list）
                if isinstance(fname_result, list):
                    # 多个文件名：需要生成多个子文件
                    fname_list = fname_result
                else:
                    # 单个文件名或None
                    fname_list = [fname_result] if fname_result else []
                
                # 如果没有从正则提取到文件名，使用备用方案
                if not fname_list:
                    drawing_number = None
                    is_mm_filtered_digit_start = False
                    drawing_result = self.number_extractor.extract_drawing_number_from_region(region)
                    drawing_number = drawing_result['drawing_number']
                    is_from_bottom_right = drawing_result['is_from_bottom_right']
                    
                    # 检查是否为MM且来自右下角区域
                    if drawing_number == 'MM' and is_from_bottom_right:
                        # 过滤掉MM，尝试备用方案1：从加工说明提取数字或大写字母开头的编号
                        texts = region.get('texts', [])
                        backup_drawing_number = self.number_extractor._extract_from_processing_instruction_with_number(texts)
                        if backup_drawing_number:
                            drawing_number = backup_drawing_number
                            # 检查是否为数字开头的编号
                            if drawing_number and drawing_number[0].isdigit():
                                is_mm_filtered_digit_start = True
                            fname = self.number_extractor.generate_safe_filename(drawing_number)
                        else:
                            # 备用方案1失败，不设置图纸编号，后续会使用调换后的厂内模号
                            drawing_number = None
                            fname = region_id
                    elif drawing_number:
                        fname = self.number_extractor.generate_safe_filename(drawing_number)
                    else:
                        fname = region_id

                    # 保底方案：如果正常流程没有提取到编号（fname为region_id），尝试从加工说明中提取三位数字
                    if not fname or fname == region_id:
                        texts = region.get('texts', [])
                        backup_number = self._extract_three_digit_from_processing_instruction(texts)
                        if backup_number:
                            fname = backup_number
                            print(f"  [保底方案] 从加工说明提取到三位数字: {backup_number}")
                        else:
                            fname = region_id
                    
                    fname_list = [fname]

                # 内部存储使用原始下划线，用于后续比较
                region_factory_model = region.get('factory_model_number')
                is_from_region = region.get('factory_model_from_region', False)
                is_from_common = region.get('factory_model_from_common', False)
                factory_model = None
                if region_factory_model:
                    # 使用第一个文件名来计算厂内模号
                    first_fname = normalize_name_internal(fname_list[0])
                    # MM过滤后提取到数字开头的编号，不对厂内模号进行去重
                    if 'MM' in str(region.get('drawing_number', '')):
                        factory_model = normalize_name_internal(region_factory_model)
                    # 备用方案2：MM过滤后，drawing_number为None且fname为region_id且is_from_region为True
                    elif region.get('drawing_number') is None and first_fname == region_id and is_from_region:
                        factory_model = normalize_name_internal(region_factory_model)
                        factory_model = self._swap_factory_model_parts(factory_model, first_fname, is_from_region, force_swap=True)
                    elif is_from_region and (first_fname == region_id or len(first_fname) == 1):
                        factory_model = normalize_name_internal(region_factory_model)
                        factory_model = self._swap_factory_model_parts(factory_model, first_fname, is_from_region)
                    # 来自最常见的厂内模号或来自块属性，直接使用，不做清洗和调换
                    elif is_from_common or region.get('factory_model_from_block'):
                        factory_model = normalize_name_internal(region_factory_model)
                    else:
                        factory_model = normalize_name_internal(self._clean_factory_model_number(region_factory_model, first_fname))

                def unique_path(path: str) -> str:
                    """生成唯一路径，如果文件已存在则在文件名后添加序号"""
                    if not os.path.exists(path):
                        return path
                    root, ext = os.path.splitext(path)
                    k = 2
                    while True:
                        cand = f"{root}({k}){ext}"
                        if not os.path.exists(cand):
                            return cand
                        k += 1

                # 为每个文件名生成一个子文件
                for fname in fname_list:
                    # 内部存储使用原始下划线，用于后续比较
                    fname_internal = normalize_name_internal(fname)
                    
                    # 生成最终文件名：将内部下划线替换为短横线
                    # 备用方案2：drawing_number为None且fname为region_id且is_from_region为True且factory_model存在
                    if region.get('drawing_number') is None and fname_internal == region_id and is_from_region and factory_model:
                        filename = f"{sanitize_filename(factory_model)}.dxf"
                    elif factory_model:
                        if is_from_region and (fname_internal == region_id or len(fname_internal) == 1):
                            filename = f"{sanitize_filename(factory_model)}.dxf"
                        else:
                            filename = f"{sanitize_filename(fname_internal)}-{sanitize_filename(factory_model)}.dxf"
                    else:
                        filename = f"{sanitize_filename(fname_internal)}.dxf"
                    save_path = unique_path(os.path.join(output_dir, filename))
                    new_doc.saveas(save_path)

                    print(f"[OK] 子图 {region_id} 已导出：{save_path}")
                    print(f"    导出实体数量: {len(selected_entities)}")

                    export_count += 1
                
                region['exported_dxf'] = save_path
                region['export_basename'] = fname_list[0]

            print(f"\n导出完成：共导出 {export_count} 个满足条件的子图")
            return output_dir

        def _extract_layer_colors(self, doc):
            # 提取所有图层的颜色信息
            print("正在提取图层颜色信息...")
            try:
                for layer in doc.layers:
                    self.layer_colors[layer.dxf.name] = getattr(layer.dxf, 'color', 7)
                print(f"图层颜色信息提取完成: {len(self.layer_colors)} 个图层")
            except Exception as e:
                print(f"图层颜色提取失败: {e}")

        def _extract_all_entities_and_texts(self, msp):
            """
            优化：一次遍历同时提取几何实体和文字实体
            时间复杂度：O(n) (原来需要两次遍历 O(2n))
            """
            print("正在提取实体和文字（优化模式：一次遍历）...")

            # 定义需要提取的实体类型
            geometric_types = {'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE', 'SPLINE', 'INSERT'}
            text_types = {'TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF'}
            # 统计计数器
            entity_count = 0
            text_count = 0
            # 一次遍历处理所有实体
            for entity in msp:
                try:
                    entity_type = entity.dxftype()

                    # 处理几何实体
                    if entity_type in geometric_types:
                        info = self._process_geometric_entity(entity)
                        if info:
                            self.all_entities.append(info)
                            entity_count += 1

                    # 处理文字实体
                    elif entity_type in text_types:
                        info = self._process_text_entity(entity)
                        if info:
                            self.all_texts.append(info)
                            text_count += 1

                except Exception:
                    # 静默跳过处理失败的实体
                    continue
            print(f"提取完成: 几何实体 {entity_count} 个, 文字实体 {text_count} 个")

        def _process_geometric_entity(self, entity) -> Optional[Dict]:
            # 处理单个几何实体，返回字典信息
            try:
                t = entity.dxftype()
                layer = getattr(entity.dxf, 'layer', '0')
                color = getattr(entity.dxf, 'color', 256)
                handle = getattr(entity.dxf, 'handle', 'N/A')
                linetype = getattr(entity.dxf, 'linetype', 'ByLayer')
                center = self._calculate_entity_center(entity)
                perimeter = self._calculate_entity_perimeter(entity)

                entity_info = {
                    'type': t, 'layer': layer, 'entity_color': color, 'handle': handle,
                    'linetype': linetype, 'center': center, 'perimeter': perimeter
                }

                if t == 'INSERT':
                    entity_info['insert_entity'] = entity
                    entity_info['block_name'] = entity.dxf.name

                return entity_info
            except Exception as e:
                print(f"处理实体时出错: {e}")
                return None

        def _calculate_entity_center(self, entity):
            # 计算实体中心点
            try:
                t = entity.dxftype()
                if t in ['CIRCLE', 'ARC']:
                    c = entity.dxf.center
                    return (round(c.x, 2), round(c.y, 2))
                elif t == 'LINE':
                    s, e = entity.dxf.start, entity.dxf.end
                    return (round((s.x + e.x) / 2, 2), round((s.y + e.y) / 2, 2))
                elif t in ['LWPOLYLINE', 'POLYLINE']:
                    pts = self._get_polyline_points(entity)
                    if pts:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        return (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
                elif t == 'ELLIPSE':
                    c = entity.dxf.center
                    return (round(c.x, 2), round(c.y, 2))
                elif t == 'SPLINE':
                    pts = self._safe_spline_points(entity)
                    if len(pts) >= 2:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        return (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
                elif t == 'INSERT':
                    insert_pt = entity.dxf.insert
                    return (round(insert_pt.x, 2), round(insert_pt.y, 2))
            except Exception:
                pass
            return (0.0, 0.0)

        def _calculate_entity_perimeter(self, entity):
            # 计算实体周长
            try:
                t = entity.dxftype()
                if t == 'CIRCLE':
                    r = entity.dxf.radius
                    return round(2 * pi * r, 2)
                elif t == 'ARC':
                    r = entity.dxf.radius
                    sa = radians(entity.dxf.start_angle)
                    ea = radians(entity.dxf.end_angle)
                    if ea < sa:
                        ea += 2 * pi
                    return round(r * (ea - sa), 2)
                elif t == 'LINE':
                    s, e = entity.dxf.start, entity.dxf.end
                    return round(sqrt((e.x - s.x) ** 2 + (e.y - s.y) ** 2), 2)
                elif t in ['LWPOLYLINE', 'POLYLINE']:
                    return round(self._calculate_polyline_length(entity), 2)
                elif t == 'ELLIPSE':
                    mx = entity.dxf.major_axis
                    a = (mx.x ** 2 + mx.y ** 2 + mx.z ** 2) ** 0.5
                    ratio = float(getattr(entity.dxf, 'ratio', 0.5) or 0.5)
                    b = a * ratio
                    h = ((a - b) ** 2) / ((a + b) ** 2) if (a + b) != 0 else 0.0
                    per = pi * (a + b) * (1 + (3 * h) / (10 + (4 - 3 * h) ** 0.5))
                    return round(per, 2)
                elif t == 'SPLINE':
                    pts = self._safe_spline_points(entity)
                    if len(pts) >= 2:
                        total_length = 0.0
                        for i in range(len(pts) - 1):
                            x1, y1 = pts[i][0], pts[i][1]
                            x2, y2 = pts[i + 1][0], pts[i + 1][1]
                            total_length += sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        if getattr(entity.dxf, 'flags', 0) & 1 and len(pts) > 2:
                            x1, y1 = pts[-1][0], pts[-1][1]
                            x2, y2 = pts[0][0], pts[0][1]
                            total_length += sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        return round(total_length, 2)
                elif t == 'INSERT':
                    block_def = entity.doc.blocks.get(entity.dxf.name)
                    if block_def:
                        bounds = self._calculate_block_bounds(block_def, entity)
                        if bounds:
                            return 2 * (bounds['width'] + bounds['height'])
            except Exception:
                pass
            return 0.0

        def _get_polyline_points(self, entity):
            """兼容 LWPOLYLINE 和 POLYLINE 的取点方法"""
            t = entity.dxftype()
            if t == 'LWPOLYLINE':
                return entity.get_points(format='xy')
            elif t == 'POLYLINE':
                pts = []
                for v in entity.vertices:
                    loc = v.dxf.location
                    pts.append((loc.x, loc.y))
                return pts
            return []

        def _calculate_polyline_length(self, polyline):
            # 计算多段线长度
            try:
                pts = self._get_polyline_points(polyline)
                if len(pts) < 2:
                    return 0.0
                total = 0.0
                for i in range(len(pts) - 1):
                    x1, y1 = pts[i]
                    x2, y2 = pts[i + 1]
                    total += sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if getattr(polyline, 'closed', False) and len(pts) > 2:
                    x1, y1 = pts[-1]
                    x2, y2 = pts[0]
                    total += sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                return total
            except Exception:
                return 0.0

        def _process_text_entity(self, entity) -> Optional[Dict]:
            # 处理单个文字实体，返回字典信息
            try:
                content = self._extract_text_content(entity)
                if not content:
                    return None
                position = self._get_text_position(entity)
                if not position:
                    return None
                return {
                    'content': self._clean_text_content(content),
                    'position': position,
                    'entity_type': entity.dxftype(),
                    'handle': entity.dxf.handle  # 添加handle用于精确过滤
                }
            except Exception:
                return None

        def _extract_text_content(self, entity) -> Optional[str]:
            # 提取文字内容
            t = entity.dxftype()
            try:
                if t == 'TEXT':
                    return entity.dxf.text
                elif t == 'MTEXT':
                    if hasattr(entity, 'get_text'):
                        return entity.get_text()
                    elif hasattr(entity, 'plain_text'):
                        return entity.plain_text()
                    return getattr(entity.dxf, 'text', None)
                elif t in ['ATTRIB', 'ATTDEF']:
                    return entity.dxf.text
            except Exception:
                pass
            return None

        def _get_text_position(self, entity) -> Optional[Tuple[float, float]]:
            # 获取文字位置
            try:
                if hasattr(entity.dxf, 'insert'):
                    p = entity.dxf.insert
                    return (float(p.x), float(p.y))
                elif hasattr(entity.dxf, 'position'):
                    p = entity.dxf.position
                    return (float(p.x), float(p.y))
                elif hasattr(entity.dxf, 'start'):
                    p = entity.dxf.start
                    return (float(p.x), float(p.y))
            except Exception:
                pass
            return None

        def _clean_text_content(self, content: str) -> str:
            # 清理文字内容
            if not content:
                return ""
            content = re.sub(r'\{\\[^}]*\}', '', content)
            content = re.sub(r'\\[A-Za-z][^;]*;', '', content)
            repl = {'%%c': 'Φ', '%%C': 'Φ', '%%d': '°', '%%D': '°', '%%p': '±', '%%P': '±', '%%u': '', '%%U': '',
                    '%%o': '', '%%O': ''}
            for k, v in repl.items():
                content = content.replace(k, v)
            return re.sub(r'\s+', ' ', content).strip()

        def set_classify_map(self, classify: Dict[str, List[str]]):
            # 设置分类映射
            self.classify_map = classify or {}

        def _extract_scale_info(self, insert_entity) -> Dict:
            """
            从INSERT实体中提取XY缩放比例信息（Z轴不参与阈值判断）

            Args:
                insert_entity: INSERT实体对象

            Returns:
                包含XY比例信息的字典
            """
            xscale = float(getattr(insert_entity.dxf, 'xscale', 1.0))
            yscale = float(getattr(insert_entity.dxf, 'yscale', 1.0))

            return {
                'xscale': xscale,
                'yscale': yscale,
                'avg_scale': (xscale + yscale) / 2.0,
                'min_scale': min(xscale, yscale),
                'max_scale': max(xscale, yscale),
                'scale_ratio': max(xscale, yscale) / min(xscale, yscale) if min(xscale, yscale) > 0 else float('inf'),
                'is_uniform_xy': abs(xscale - yscale) < 0.01
            }

        def _identify_frame_blocks(self, msp):
            # 识别所有块引用作为图框块
            print("正在识别块图框（修复 BlockLayout 处理）...")
            self.frame_blocks = []
            self.common_factory_model_number = None
            self.most_common_factory_model = None  # 最常见的厂内模号（备用）
            all_inserts = []

            # 递归收集模型空间中所有的 INSERT（块引用）实体
            def collect_inserts(entity):
                if not hasattr(entity, 'dxftype'):
                    for child in entity:
                        collect_inserts(child)
                    return
                if entity.dxftype() == 'INSERT':
                    all_inserts.append(entity)
                if hasattr(entity, '__iter__'):
                    try:
                        for child in entity:
                            collect_inserts(child)
                    except TypeError:
                        pass

            collect_inserts(msp)
            print(f"共收集到 {len(all_inserts)} 个块引用（含匿名块）")

            # 调试：显示所有块参照的名称
            block_names_found = []
            for insert in all_inserts:
                try:
                    block_names_found.append(insert.dxf.name)
                except:
                    pass
            if block_names_found:
                print(f"[调试] 检测到的块参照名称: {', '.join(sorted(set(block_names_found)))}")

            # 遍历所有块引用，提取满足条件的图框候选
            block_candidates = []
            # 用于统计厂内模号出现次数
            factory_model_counter = Counter()

            # 统计筛选过程
            filtered_small = 0  # 尺寸太小
            filtered_aspect = 0  # 长宽比异常
            processed_count = 0  # 处理的块总数

            for idx, insert in enumerate(all_inserts):
                try:
                    processed_count += 1
                    block_name = insert.dxf.name
                    block_def = insert.doc.blocks.get(block_name)
                    if not block_def:
                        print(f"块 {block_name} 无定义，跳过")
                        continue

                    # 提取当前块参照的厂内模号
                    # 定义支持的厂内模号属性标签列表
                    factory_model_tags = ['18-**-**', '模具编号']

                    block_factory_model = None
                    try:
                        for attrib in insert.attribs:
                            if attrib.dxf.tag in factory_model_tags:
                                model_number = attrib.dxf.text.strip()
                                if model_number:
                                    model_number = re.sub(r'[^a-zA-Z0-9-]', '-', model_number)
                                    block_factory_model = model_number
                                    break
                    except Exception:
                        pass

                    bounds = self._calculate_block_bounds(block_def, insert)
                    if not bounds:
                        print(f"块 {block_name} 无法计算边界，跳过")
                        continue

                    # 提取XY比例信息
                    scale_info = self._extract_scale_info(insert)

                    if self._is_valid_frame_block(bounds, scale_info):
                        block_candidate = {
                            'type': 'block',
                            'block_name': block_name,
                            'insert_point': (insert.dxf.insert.x, insert.dxf.insert.y),
                            'bounds': bounds,
                            'insert_entity': insert,
                            'scale_info': scale_info,
                            'factory_model': block_factory_model  # 存储当前块参照的厂内模号
                        }
                        block_candidates.append(block_candidate)

                        # 统计厂内模号出现次数
                        if block_factory_model:
                            factory_model_counter[block_factory_model] += 1
                    else:
                        # 统计被过滤的块
                        min_size = 30.0 * (scale_info.get('avg_scale', 1.0) if scale_info else 1.0)
                        if bounds and (bounds['width'] <= min_size or bounds['height'] <= min_size):
                            filtered_small += 1
                        elif bounds:
                            aspect_ratio = bounds['width'] / bounds['height'] if bounds['height'] != 0 else 0
                            if aspect_ratio <= 0.2 or aspect_ratio >= 5.0:
                                filtered_aspect += 1

                except Exception as e:
                    print(f"处理块 {insert.dxf.name if hasattr(insert.dxf, 'name') else '未知'} 时出错: {e}")
                    continue

            # 计算最常见的厂内模号
            if factory_model_counter:
                self.most_common_factory_model = factory_model_counter.most_common(1)[0][0]

            # 统计：打印筛选结果
            print(f"[图框筛选] 处理的块引用总数: {processed_count}")
            print(f"[图框筛选] 提取的候选图框块数量: {len(block_candidates)}")
            print(f"[图框筛选] 被过滤的块数量 - 尺寸太小: {filtered_small}, 长宽比异常: {filtered_aspect}")

            self.frame_blocks = self._deduplicate_frames(block_candidates)
            print(f"[图框筛选] 去重后的有效图框块数量: {len(self.frame_blocks)}")

            # 打印每个有效图框的详细信息
            if self.frame_blocks:
                print(f"[图框详情] 有效图框列表:")
                for i, frame in enumerate(self.frame_blocks, 1):
                    block_name = frame.get('block_name', '未知')
                    insert_point = frame.get('insert_point', (0, 0))
                    width = frame['bounds']['width']
                    height = frame['bounds']['height']
                    area = width * height
                    scale = frame.get('scale_info', {}).get('avg_scale', 1.0)
                    print(f"  {i}. {block_name}: 尺寸={width:.1f}×{height:.1f}, 面积={area:.0f}, 比例={scale:.2f}, 插入点=({insert_point[0]:.1f}, {insert_point[1]:.1f})")

        def _calculate_block_bounds(self, block_def, insert) -> Optional[Dict]:
            """优化的块边界计算 - 使用缓存机制避免重复计算"""
            block_name = block_def.dxf.name

            # 1. 从缓存获取或计算块定义的本地边界（不考虑变换）
            if block_name not in self._block_local_bounds_cache:
                self._block_local_bounds_cache[block_name] = self._calculate_block_local_bounds(block_def)

            local_bounds = self._block_local_bounds_cache[block_name]
            if not local_bounds:
                return None

            # 2. 应用INSERT的变换（缩放、旋转、平移）
            return self._transform_bounds(local_bounds, insert)

        def _calculate_block_local_bounds(self, block_def) -> Optional[Dict]:
            """计算块定义的本地边界（不考虑变换），支持嵌套块，结果可缓存"""
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            has_entities = False

            for entity in block_def:
                if entity.dxftype() == 'INSERT':
                    # 递归处理嵌套块
                    nested_block = entity.doc.blocks.get(entity.dxf.name)
                    if nested_block:
                        nested_bounds = self._calculate_block_local_bounds(nested_block)
                        if nested_bounds:
                            # ✅ 修复：应用嵌套块的变换到其边界
                            insert_x = entity.dxf.insert.x
                            insert_y = entity.dxf.insert.y
                            sx = getattr(entity.dxf, 'xscale', 1.0)
                            sy = getattr(entity.dxf, 'yscale', 1.0)
                            rotation = getattr(entity.dxf, 'rotation', 0.0)
                            rot_rad = radians(rotation)

                            # 定义嵌套块本地边界的四个角点
                            corners = [
                                (nested_bounds['min_x'], nested_bounds['min_y']),
                                (nested_bounds['max_x'], nested_bounds['min_y']),
                                (nested_bounds['min_x'], nested_bounds['max_y']),
                                (nested_bounds['max_x'], nested_bounds['max_y']),
                            ]

                            # 对每个角点应用变换：缩放 -> 旋转 -> 平移
                            transformed_corners = []
                            for x, y in corners:
                                # 缩放
                                x_scaled = x * sx
                                y_scaled = y * sy
                                # 旋转
                                x_rot = x_scaled * cos(rot_rad) - y_scaled * sin(rot_rad)
                                y_rot = x_scaled * sin(rot_rad) + y_scaled * cos(rot_rad)
                                # 平移（插入点）
                                transformed_corners.append((insert_x + x_rot, insert_y + y_rot))

                            # 计算变换后的边界
                            nested_tx = [c[0] for c in transformed_corners]
                            nested_ty = [c[1] for c in transformed_corners]
                            nested_transformed_bounds = {
                                'min_x': min(nested_tx),
                                'max_x': max(nested_tx),
                                'min_y': min(nested_ty),
                                'max_y': max(nested_ty)
                            }

                            # ✅ 使用变换后的边界进行累加
                            min_x = min(min_x, nested_transformed_bounds['min_x'])
                            max_x = max(max_x, nested_transformed_bounds['max_x'])
                            min_y = min(min_y, nested_transformed_bounds['min_y'])
                            max_y = max(max_y, nested_transformed_bounds['max_y'])
                            has_entities = True
                else:
                    # 处理普通实体
                    entity_bounds = self._get_entity_local_bounds(entity)
                    if entity_bounds:
                        min_x = min(min_x, entity_bounds['min_x'])
                        max_x = max(max_x, entity_bounds['max_x'])
                        min_y = min(min_y, entity_bounds['min_y'])
                        max_y = max(max_y, entity_bounds['max_y'])
                        has_entities = True

            if not has_entities:
                return None

            # 强制转换为Python原生float类型,避免numpy类型导致的后续问题
            return {
                'min_x': float(min_x), 'max_x': float(max_x),
                'min_y': float(min_y), 'max_y': float(max_y)
            }

        def _transform_bounds(self, local_bounds: Dict, insert) -> Dict:
            """应用INSERT的变换到本地边界"""
            sx = getattr(insert.dxf, 'xscale', 1.0)
            sy = getattr(insert.dxf, 'yscale', 1.0)
            rotation = getattr(insert.dxf, 'rotation', 0.0)
            rot_rad = radians(rotation)
            insert_pt = insert.dxf.insert

            # 定义本地边界的四个角点
            corners = [
                (local_bounds['min_x'], local_bounds['min_y']),
                (local_bounds['max_x'], local_bounds['min_y']),
                (local_bounds['min_x'], local_bounds['max_y']),
                (local_bounds['max_x'], local_bounds['max_y']),
            ]

            # 对每个角点应用变换：缩放 -> 旋转 -> 平移
            world_corners = []
            for x, y in corners:
                # 缩放
                x_scaled = x * sx
                y_scaled = y * sy
                # 旋转
                x_rot = x_scaled * cos(rot_rad) - y_scaled * sin(rot_rad)
                y_rot = x_scaled * sin(rot_rad) + y_scaled * cos(rot_rad)
                # 平移
                world_corners.append((insert_pt.x + x_rot, insert_pt.y + y_rot))

            # 计算变换后的边界
            xs = [c[0] for c in world_corners]
            ys = [c[1] for c in world_corners]

            return {
                'min_x': float(min(xs)), 'max_x': float(max(xs)),
                'min_y': float(min(ys)), 'max_y': float(max(ys)),
                'width': float(max(xs) - min(xs)), 'height': float(max(ys) - min(ys))
            }

        def _precalculate_all_block_bounds(self, doc):
            """
            性能优化：预计算所有块定义的边界
            避免在拆图过程中动态计算块边界，提升处理包含大量块的 DXF 文件的性能
            """
            print("正在预计算所有块定义的边界...")
            block_count = 0
            success_count = 0

            for block in doc.blocks:
                block_name = block.dxf.name

                # 跳过模型空间和图纸空间
                if block_name in ('*Model_Space', '*Paper_Space', '*Paper_Space0'):
                    continue

                block_count += 1

                # 如果该块边界还未计算，则进行计算
                if block_name not in self._block_local_bounds_cache:
                    try:
                        self._block_local_bounds_cache[block_name] = self._calculate_block_local_bounds(block)
                        if self._block_local_bounds_cache[block_name]:
                            success_count += 1
                    except Exception as e:
                        print(f"  预计算块 '{block_name}' 边界失败: {e}")

            print(f"块边界预计算完成，共 {block_count} 个块定义，成功缓存 {success_count} 个")

        def _get_entity_local_bounds(self, entity) -> Optional[Dict]:
            """
            获取实体本地边界（带缓存优化）
            性能优化：避免重复计算相同实体的边界
            """
            # 尝试从缓存获取
            handle = entity.dxf.handle
            if handle in self._block_entity_bounds_cache:
                return self._block_entity_bounds_cache[handle]

            # 缓存未命中，计算边界
            try:
                t = entity.dxftype()
                bounds = None

                if t == 'LINE':
                    s, e = entity.dxf.start, entity.dxf.end
                    bounds = {
                        'min_x': min(s.x, e.x), 'max_x': max(s.x, e.x),
                        'min_y': min(s.y, e.y), 'max_y': max(s.y, e.y)
                    }
                elif t in ['CIRCLE', 'ARC']:
                    c = entity.dxf.center
                    r = entity.dxf.radius
                    bounds = {
                        'min_x': c.x - r, 'max_x': c.x + r,
                        'min_y': c.y - r, 'max_y': c.y + r
                    }
                elif t in ['LWPOLYLINE', 'POLYLINE']:
                    pts = self._get_polyline_points(entity)
                    if pts:
                        xs, ys = zip(*pts)
                        bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}
                elif t == 'ELLIPSE':
                    c = entity.dxf.center
                    major = entity.dxf.major_axis
                    ratio = getattr(entity.dxf, 'ratio', 0.5)
                    a = (major.x ** 2 + major.y ** 2) ** 0.5
                    b = a * ratio
                    bounds = {'min_x': c.x - a, 'max_x': c.x + a, 'min_y': c.y - b, 'max_y': c.y + b}
                elif t == 'SPLINE':
                    pts = self._safe_spline_points(entity)
                    if pts:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}

                # 存入缓存
                if bounds:
                    self._block_entity_bounds_cache[handle] = bounds
                return bounds

            except Exception as e:
                print(f"获取实体本地边界出错 ({entity.dxftype()}): {e}")
            return None

        def _extract_three_digit_from_processing_instruction(self, texts: List) -> Optional[str]:
            """保底方案：从加工说明中提取三位数字（如：加工说明:(上夹板块)_117）"""
            # 匹配加工说明后面的下划线或括号后的三位数字
            pattern = re.compile(r'加工说明[:：][\s_（）()\u4e00-\u9fa5/|｜]*[_\(（](?:[^\)]*[\)）])?[_\s]*(\d{3})')

            for text in texts:
                content = text['content'].strip()
                match = pattern.search(content)
                if match:
                    number = match.group(1)
                    # 确保是三位数字
                    if re.match(r'^\d{3}$', number):
                        return number
            return None

        def _is_valid_frame_block(self, bounds: Dict, scale_info: Dict = None) -> bool:
            """
            判断块是否为有效图框（支持动态阈值）

            Args:
                bounds: 边界字典（只包含几何信息）
                scale_info: 比例信息字典（可选），包含xscale, yscale, avg_scale等

            Returns:
                是否为有效图框
            """
            # 基础阈值
            base_min_size = 30.0
            aspect_ratio_min = 0.2
            aspect_ratio_max = 5.0

            # 根据比例信息动态调整最小尺寸阈值
            if scale_info and 'avg_scale' in scale_info:
                min_size = base_min_size * scale_info['avg_scale']
            else:
                min_size = base_min_size

            aspect_ratio = bounds['width'] / bounds['height'] if bounds['height'] != 0 else 0

            return (bounds['width'] > min_size and
                    bounds['height'] > min_size and
                    aspect_ratio_min < aspect_ratio < aspect_ratio_max)

        def _deduplicate_frames(self, candidates):
            # 图框去重 - 考虑比例差异，避免删除不同比例的独立子图
            if len(candidates) <= 1:
                return candidates

            # 过滤无效图框：面积太小、比例异常、匿名块
            valid_candidates = []
            min_valid_area = 10000  # 最小有效面积阈值

            for c in candidates:
                

                scale_info = c.get('scale_info', {})
                avg_scale = scale_info.get('avg_scale', 1.0)
                area = c['bounds']['width'] * c['bounds']['height']

                # 过滤条件：面积太小 或 比例异常
                if area < min_valid_area:
                    continue

                valid_candidates.append(c)

            candidates = valid_candidates

            if len(candidates) <= 1:
                return candidates

            # 按面积从大到小排序
            candidates.sort(key=lambda x: (x['bounds']['width'] * x['bounds']['height']), reverse=True)
            unique = [candidates[0]]

            # 配置参数
            SCALE_DIFF_THRESHOLD = 0.2   # 比例差异阈值：20%
            AREA_RATIO_THRESHOLD = 0.3   # 面积比例阈值：小图<大图30%时保留

            for c in candidates[1:]:
                c_bounds = c['bounds']
                c_scale_info = c.get('scale_info', {})
                c_scale = c_scale_info.get('avg_scale', 1.0)
                c_area = c_bounds['width'] * c_bounds['height']

                should_skip = False

                for u in unique:
                    u_bounds = u['bounds']
                    u_scale_info = u.get('scale_info', {})
                    u_scale = u_scale_info.get('avg_scale', 1.0)
                    u_area = u_bounds['width'] * u_bounds['height']

                    # 计算重叠面积
                    overlap_min_x = max(c_bounds['min_x'], u_bounds['min_x'])
                    overlap_max_x = min(c_bounds['max_x'], u_bounds['max_x'])
                    overlap_min_y = max(c_bounds['min_y'], u_bounds['min_y'])
                    overlap_max_y = min(c_bounds['max_y'], u_bounds['max_y'])

                    if overlap_min_x < overlap_max_x and overlap_min_y < overlap_max_y:
                        # 检查当前块是否完全在已保留块的内部（内部块特征）
                        c_inside_u = (c_bounds['min_x'] >= u_bounds['min_x'] and
                                     c_bounds['max_x'] <= u_bounds['max_x'] and
                                     c_bounds['min_y'] >= u_bounds['min_y'] and
                                     c_bounds['max_y'] <= u_bounds['max_y'])

                        if c_inside_u:
                            # 关键改进：检查比例差异和面积比例
                            scale_diff = abs(c_scale - u_scale) / max(c_scale, u_scale)
                            area_ratio = c_area / u_area

                            # 情况1：比例差异大 → 不同比例的独立图纸，保留
                            if scale_diff > SCALE_DIFF_THRESHOLD:
                                continue  # 跳过这个u，继续检查下一个

                            # 情况2：面积差异大 → 可能是小子图，保留
                            if area_ratio < AREA_RATIO_THRESHOLD:
                                continue

                            # 情况3：比例相近且面积相仿 → 确认是重复，删除
                            should_skip = True
                            break

                if not should_skip:
                    unique.append(c)

            return unique


        def _create_subdrawing_regions(self):
            # 根据图框块创建子图区域并筛选
            """创建子图区域时直接应用筛选条件"""
            self.frame_blocks.sort(key=self._get_spatial_sort_key)
            valid_count = 0

            for i, fb in enumerate(self.frame_blocks):
                rid = f"subdrawing_{i + 1:03d}"

                # 获取当前块参照的厂内模号
                block_factory_model = fb.get('factory_model')

                region_data = {
                    'frame_block': fb,
                    'bounds': fb['bounds'],
                    'texts': [],
                    'cutting_analysis': {},
                    'factory_model_number': block_factory_model,  # 从块参照获取厂内模号
                    'factory_model_from_block': True if block_factory_model else False  # 标记是否来自块属性
                }

                self._assign_texts_to_single_region(region_data)

                if self._should_process_region(region_data):
                    self.sub_drawings[rid] = region_data
                    valid_count += 1
                    # print(f"区域 {rid} 满足条件，将被处理")
                else:
                    # print(f"区域 {rid} 不满足条件，跳过")
                    pass

            # print(f"区域创建完成：{len(self.frame_blocks)} 个图框，{valid_count} 个满足条件")

        def _assign_texts_to_single_region(self, region_data: Dict):
            # 为单个区域分配文字
            """为单个区域分配文字"""
            bounds = region_data['bounds']
            region_texts = []

            for text in self.all_texts:
                x, y = text['position']
                if (bounds['min_x'] <= x <= bounds['max_x'] and
                        bounds['min_y'] <= y <= bounds['max_y']):
                    region_texts.append(text)

            region_data['texts'] = self.text_processor.process_text_list(region_texts)

        def _get_spatial_sort_key(self, frame_block):
            # 区域空间排序键
            b = frame_block['bounds']
            tol = 100
            return (-round(b['min_y'] / tol), round(b['min_x'] / tol))

        def _assign_texts_to_regions(self):
            """分配文字到区域"""
            print("正在分配文字到区域...")

            for text in self.all_texts:
                text_x, text_y = text['position']
                assigned = False

                # 查找包含文字的区域
                for region_id, region_data in self.sub_drawings.items():
                    bounds = region_data['bounds']

                    if (bounds['min_x'] <= text_x <= bounds['max_x'] and
                            bounds['min_y'] <= text_y <= bounds['max_y']):
                        region_data['texts'].append(text)
                        assigned = True
                        break

                # 分配到最近区域
                if not assigned:
                    closest_region = self._find_closest_region((text_x, text_y))
                    if closest_region:
                        self.sub_drawings[closest_region]['texts'].append(text)

            # 处理各区域文字
            for region_id, region_data in self.sub_drawings.items():
                original_count = len(region_data['texts'])
                region_data['texts'] = self.text_processor.process_text_list(
                    region_data['texts'])
                processed_count = len(region_data['texts'])

                # print(f"区域 {region_id}: 处理前 {original_count} 个文字，"
                #     f"处理后 {processed_count} 个文字")
                
        def _analyze_cutting_contours_for_regions(self):
            """为各区域分析切割轮廓"""
            print("正在分析各区域的切割轮廓（采用严格策略）...")

            for region_id, region_data in self.sub_drawings.items():
                bounds = region_data['bounds']

                # 检测该区域的切割轮廓
                cutting_result = self.cutting_detector.detect_cutting_contours_in_region(
                    bounds, self.all_entities, self.layer_colors)

                region_data['cutting_analysis'] = cutting_result

                # print(f"区域 {region_id}: 检测到 {cutting_result['contour_count']} 个切割轮廓，"
                #     f"总长度 {cutting_result['total_cutting_length']:.2f}mm")


        def _find_closest_region(self, pos: Tuple[float, float]) -> Optional[str]:
            # 查找最近区域
            x, y = pos
            md = float('inf')
            cid = None
            for rid, r in self.sub_drawings.items():
                b = r['bounds']
                cx = (b['min_x'] + b['max_x']) / 2
                cy = (b['min_y'] + b['max_y']) / 2
                d = sqrt((x - cx) ** 2 + (y - cy) ** 2)
                if d < md:
                    md = d
                    cid = rid
            return cid

        def _extract_factory_model_number_from_regions(self):
            """从子图区域右下角提取厂内模号"""
            for region_id, region_data in self.sub_drawings.items():
                # 如果已经有来自块属性的厂内模号，跳过提取
                if region_data.get('factory_model_from_block'):
                    continue

                bounds = region_data['bounds']
                texts = region_data.get('texts', [])

                if not texts:
                    # 没有文本，尝试使用最常见的厂内模号
                    if self.most_common_factory_model:
                        region_data['factory_model_number'] = self.most_common_factory_model
                        region_data['factory_model_from_common'] = True
                    continue

                min_x, max_x = bounds['min_x'], bounds['max_x']
                min_y, max_y = bounds['min_y'], bounds['max_y']

                width = max_x - min_x
                height = max_y - min_y

                right_bottom_x = max_x - width * 0.2
                right_bottom_y = min_y + height * 0.2

                found_in_region = False
                for text in texts:
                    content = text.get('content', '').strip()
                    if not content:
                        continue

                    x, y = text['position']

                    if x >= right_bottom_x and y <= right_bottom_y:
                        if re.match(r'^[A-Z]', content) and len(content) > 3:
                            region_data['factory_model_number'] = content
                            region_data['factory_model_from_region'] = True
                            region_data['factory_model_handle'] = text.get('handle')  # 记录handle用于导出时过滤
                            found_in_region = True
                            break

                # 如果没有从右下角提取到，尝试使用最常见的厂内模号
                if not found_in_region and self.most_common_factory_model:
                    region_data['factory_model_number'] = self.most_common_factory_model
                    region_data['factory_model_from_common'] = True

        def _clean_factory_model_number(self, factory_model: str, drawing_number: str) -> str:
            """清洗厂内模号，去除末尾与图纸编号重复的部分（内部格式使用下划线）"""
            if not factory_model or not drawing_number:
                return factory_model

            drawing_length = len(drawing_number)
            if len(factory_model) <= drawing_length:
                return factory_model

            suffix = factory_model[-drawing_length:]
            if suffix == drawing_number:
                cleaned = factory_model[:-drawing_length]
                # 清理末尾的下划线或短横线
                cleaned = re.sub(r'[_-]+$', '', cleaned)
                return cleaned

            return factory_model

        def _swap_factory_model_parts(self, factory_model: str, drawing_number: str, is_from_region: bool, force_swap: bool = False) -> str:
            """调换厂内模号中"_"前后的内容（内部格式使用下划线）

            Args:
                factory_model: 厂内模号（内部格式，使用下划线）
                drawing_number: 图纸编号
                is_from_region: 是否来自右下角区域提取
                force_swap: 是否强制调换（忽略其他条件）

            Returns:
                调换后的厂内模号，如果不满足条件则返回原值
            """
            if not factory_model:
                return factory_model

            # 强制调换模式：只要来自右下角区域且有"_"连接符就调换
            if force_swap:
                if not is_from_region:
                    return factory_model
                parts = factory_model.split('_')
                if len(parts) >= 2:
                    swapped = f"{parts[1]}_{parts[0]}"
                    return swapped
                return factory_model

            # 原有逻辑：根据图纸编号长度决定是否调换
            if not is_from_region:
                return factory_model

            if drawing_number and len(drawing_number) != 1:
                return factory_model

            parts = factory_model.split('_')
            if len(parts) != 2:
                return factory_model

            swapped = f"{parts[1]}_{parts[0]}"
            return swapped


    class StrictCuttingDetector:
        """严格的切割轮廓检测器 - 仅识别直接红色实体"""

        def __init__(self):
            # 切割相关颜色代码（红色系）
            self.cutting_colors = [1]

            # 明确排除的图层模式
            self.exclude_layer_patterns = [
                r'.*text.*', r'.*dim.*', r'.*annotation.*', r'.*title.*',
                r'.*border.*', r'.*frame.*', r'.*标注.*', r'.*文字.*', r'.*尺寸.*',
                r'.*defpoints.*'  # AutoCAD默认点图层
            ]

            # 几何实体类型
            self.geometric_entities = ['LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE']
            self.BYLAYER_COLOR = 256

            # 图层颜色映射
            self.layer_colors = {}

        def detect_cutting_contours_in_region(self, region_bounds: Dict, all_entities: List,
                                            layer_colors: Dict) -> Dict:
            """检测指定区域内的切割轮廓 - 采用严格策略"""
            self.layer_colors = layer_colors

            # 获取区域内的所有几何实体
            region_entities = self._get_entities_in_bounds(all_entities, region_bounds)

            # 采用严格策略识别红色实体
            red_entities = []
            for entity in region_entities:
                if self._is_red_geometric_entity_strict(entity):
                    red_entities.append(entity)

            # 分类实体
            cutting_contours = []
            auxiliary_marks = []

            for entity_info in red_entities:
                if self._should_exclude_entity(entity_info):
                    auxiliary_marks.append(entity_info)
                else:
                    cutting_contours.append(entity_info)

            # 计算统计数据
            total_cutting_length = sum(e.get('perimeter', 0) for e in cutting_contours)
            contour_count = len(cutting_contours)

            return {
                'cutting_contours': cutting_contours,
                'auxiliary_marks': auxiliary_marks,
                'total_cutting_length': round(total_cutting_length, 2),
                'contour_count': contour_count,
                'contour_types': self._get_contour_types(cutting_contours),
                'cutting_analysis': self._generate_cutting_analysis(cutting_contours)
            }

        def _get_entities_in_bounds(self, entities: List, bounds: Dict) -> List:
            """获取边界内的实体"""
            region_entities = []

            for entity_info in entities:
                center = entity_info.get('center', (0, 0))
                if (bounds['min_x'] <= center[0] <= bounds['max_x'] and
                        bounds['min_y'] <= center[1] <= bounds['max_y']):
                    region_entities.append(entity_info)

            return region_entities

        def _is_red_geometric_entity_strict(self, entity_info: Dict) -> bool:
            """严格判断是否为红色几何实体（检查实体类型、颜色和线型）"""
            entity_type = entity_info.get('type', '')
            if entity_type not in self.geometric_entities:
                return False
            entity_color = entity_info.get('entity_color', self.BYLAYER_COLOR)
            if entity_color not in self.cutting_colors:
                return False
            linetype = entity_info.get('linetype', 'ByLayer')
            if linetype.lower() not in ['continuous', 'bylayer']:
                return False
            return True

        def _should_exclude_entity(self, entity_info: Dict) -> bool:
            """判断是否应该排除实体"""
            layer_name = entity_info.get('layer', '')
            layer_name_lower = layer_name.lower()

            # 排除明确的文字、标注、边框图层
            for pattern in self.exclude_layer_patterns:
                if re.match(pattern, layer_name_lower, re.IGNORECASE):
                    return True

            return False

        def _get_contour_types(self, contours: List) -> Dict:
            """获取轮廓类型分布"""
            type_count = defaultdict(int)
            for contour in contours:
                type_count[contour.get('type', 'UNKNOWN')] += 1
            return dict(type_count)

        def _generate_cutting_analysis(self, contours: List) -> Dict:
            """生成切割分析数据"""
            if not contours:
                return {'summary': '未检测到切割轮廓'}

            perimeters = [c.get('perimeter', 0) for c in contours if c.get('perimeter', 0) > 0]

            analysis = {
                'total_length': sum(perimeters),
                'contour_count': len(contours),
                'avg_length': sum(perimeters) / len(perimeters) if perimeters else 0,
                'min_length': min(perimeters) if perimeters else 0,
                'max_length': max(perimeters) if perimeters else 0
            }

            # 生成描述性摘要
            if analysis['contour_count'] > 0:
                analysis['summary'] = (f"检测到{analysis['contour_count']}个切割轮廓，"
                                    f"总长度{analysis['total_length']:.2f}mm")
            else:
                analysis['summary'] = "未检测到有效切割轮廓"

            return analysis

    # 2D拆图主逻辑
    def IntegralMoudle_Splitting(input_file: str, output_root: str):
        """集成CAD子图分析与切割轮廓检测主函数"""
        import time
        total_start = time.perf_counter()

        print("集成CAD子图分析与切割轮廓检测系统")
        print("=" * 60)
        print(f"输入整图: {input_file}")
        print(f"子图DXF输出目录: {output_root}")

        if not os.path.exists(input_file):
            print(f"错误：文件不存在 - {input_file}")
            return None
        if not input_file.lower().endswith('.dxf'):
            print("错误：仅支持DXF格式文件，请先转换DWG为DXF")
            return None

        # 阶段1: 文件读取
        step1_start = time.perf_counter()
        try:
            doc = ezdxf.readfile(input_file)
            print(f"调试：DXF版本 {doc.dxfversion}，单位 {doc.units}")
            print(f"调试：模型空间实体总数 {len(list(doc.modelspace()))}")
        except Exception as e:
            print(f"读取文件信息失败：{e}")
        step1_time = time.perf_counter() - step1_start

        # 阶段2: CAD分析
        step2_start = time.perf_counter()
        analyzer = OptimizedCADBlockAnalyzer()
        results = analyzer.analyze_cad_file(input_file)
        if not results:
            print("未提取到任何满足条件的子图信息，可能原因：")
            print("1. 图框不包含'加工说明'文字")
            print("2. 图框包含排除词汇（厂内标准件、订购、装配、组配）")
            print("3. 图框不是块引用，且线条组合未被识别")
            print("4. 图框尺寸小于最小阈值（当前30单位）")
            return None
        step2_time = time.perf_counter() - step2_start

        # 阶段3: 导出子图
        step3_start = time.perf_counter()
        if not output_root:
            output_root = os.path.join(os.path.dirname(input_file), "subdrawings_dxf")
        os.makedirs(output_root, exist_ok=True)
        print(f"\n开始导出满足条件的子图DXF到目录：{output_root}")

        exported_dir = analyzer.export_regions_to_dxf(output_root)
        step3_time = time.perf_counter() - step3_start
        # 统计总耗时
        total_time = time.perf_counter() - total_start
        print(f"\n分析与导出完成！子图DXF目录: {exported_dir}")
        print(f"⏱️ 运行时间总耗时: {total_time:.2f}秒")
        return exported_dir

else:
    # ezdxf不可用时的占位函数
    def IntegralMoudle_Splitting(input_file: str, output_root: str):
        print("ezdxf 库未加载，跳过 2D 图纸拆分。")
        return None
    
# ==============================================================================
# 包装函数
# ==============================================================================

def split_dxf_file_with_output(input_dxf: str, output_dir: str):
    """DXF文件拆分入口函数"""
    if not EZDXF_AVAILABLE:
        print("错误: ezdxf库未安装，无法进行DXF拆分")
        return None
    if not os.path.exists(input_dxf):
        print(f"错误: 输入文件不存在 - {input_dxf}")
        return None
    result = IntegralMoudle_Splitting(input_dxf, output_dir)
    import gc
    gc.collect()
    return result

def main():
    """独立运行入口"""
    # 测试路径配置
    input_dxf = r"D:\dxf\M250088-箱底顶板OP40总图2025.05.30.dxf"

    output_dir = r'D:\dxf\ocr'

    result = split_dxf_file_with_output(input_dxf, output_dir)
    if result:
        print(f"\n✅ DXF拆分完成！\n   输出目录: {result}")
    else:
        print("\n❌ DXF拆分失败")

if __name__ == "__main__":
    main()  

    