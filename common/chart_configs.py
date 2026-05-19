# common/chart_configs.py
"""
Standardized chart configurations for Shadcn charts
"""
from typing import Dict, List

class ChartConfig:
    """Standardized chart configuration"""
    
    AREA = "area"
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    DONUT = "donut"
    RADAR = "radar"
    
    @staticmethod
    def create_config(chart_type: str, title: str, description: str, 
                     data_key: str, color: str = None) -> Dict:
        """Create standard chart configuration"""
        return {
            "title": title,
            "description": description,
            "type": chart_type,
            "config": {
                data_key: {
                    "label": title,
                    "color": color or "hsl(var(--chart-1))"
                }
            }
        }
    
    @staticmethod
    def format_for_shadcn(data: List[Dict], config: Dict) -> Dict:
        """Format data for Shadcn chart components"""
        return {
            "data": data,
            **config
        }


class ColorPalette:
    """Consistent color palette for charts"""
    
    COLORS = [
        "hsl(var(--chart-1))",
        "hsl(var(--chart-2))",
        "hsl(var(--chart-3))",
        "hsl(var(--chart-4))",
        "hsl(var(--chart-5))",
    ]
    
    @classmethod
    def get_color(cls, index: int) -> str:
        """Get color by index"""
        return cls.COLORS[index % len(cls.COLORS)]
    
    @classmethod
    def add_colors_to_data(cls, data: List[Dict], key: str = 'fill') -> List[Dict]:
        """Add colors to data items"""
        return [
            {**item, key: cls.get_color(i)}
            for i, item in enumerate(data)
        ]