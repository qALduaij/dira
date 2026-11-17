"""Fictional bilingual scenarios; these are never presented as real news."""

from datetime import timedelta
from .models import TDO, Entity, utcnow

CHANNELS = [
    {
        "id": "ktv1",
        "name": "Kuwait TV",
        "name_ar": "تلفزيون الكويت",
        "short": "KTV 1",
        "region": "Kuwait",
        "color": "#c6ac70",
        "category": "National",
    },
    {
        "id": "gulf",
        "name": "Gulf News",
        "name_ar": "أخبار الخليج",
        "short": "GULF",
        "region": "Gulf",
        "color": "#6bc6bb",
        "category": "Regional",
    },
    {
        "id": "business",
        "name": "Market Watch",
        "name_ar": "رصد الأسواق",
        "short": "MARKET",
        "region": "Global",
        "color": "#9aaee2",
        "category": "Business",
    },
    {
        "id": "world",
        "name": "World Desk",
        "name_ar": "المشهد العالمي",
        "short": "WORLD",
        "region": "Global",
        "color": "#d09984",
        "category": "International",
    },
]
SCENARIOS = [
    (
        "افتتاح منتدى الابتكار في الكويت بمشاركة باحثين من المنطقة",
        "Kuwait innovation forum opens with researchers from across the region.",
        "الكويت تستضيف منتدى الابتكار",
        "Forum stage, speakers and Kuwait skyline",
        [("Kuwait", "location"), ("Innovation", "topic")],
    ),
    (
        "تقرير يناقش دور الموانئ الخليجية في تطوير حركة التجارة",
        "A report examines Gulf ports and their role in regional trade.",
        "الموانئ الخليجية وتطور التجارة",
        "Container ships and port cranes on the Gulf coast",
        [("Gulf ports", "organization"), ("Trade", "topic")],
    ),
    (
        "الأسواق تتابع تطورات مشاريع الطاقة المتجددة في المنطقة",
        "Markets track renewable energy projects across the region.",
        "الطاقة المتجددة في صدارة المشهد",
        "Solar panels and an energy market chart",
        [("Energy", "topic"), ("Gulf", "location")],
    ),
    (
        "عاجل: تمرين محاكاة لاستجابة الموانئ لتغير حركة الشحن",
        "Breaking: simulated port response exercise follows a change in shipping activity.",
        "عاجل | تمرين محاكاة في الموانئ",
        "Ships approaching a port during a simulation exercise",
        [("Gulf ports", "organization"), ("Shipping", "topic"), ("Kuwait", "location")],
    ),
    (
        "جامعة الكويت تعرض برامج جديدة لدعم البحث العلمي",
        "Kuwait University presents new scientific research programs.",
        "برامج جديدة لدعم البحث العلمي",
        "University campus and research laboratory",
        [("Kuwait University", "organization"), ("Research", "topic")],
    ),
    (
        "مناقشة حول استقرار أسعار النفط وتوقعات الطلب العالمي",
        "A discussion on oil price stability and global demand forecasts.",
        "النفط والطلب العالمي تحت المتابعة",
        "Energy analysts in a television studio",
        [("Energy", "topic"), ("Oil", "topic")],
    ),
    (
        "انطلاق معرض ثقافي يعرض تاريخ الملاحة في الخليج",
        "A cultural exhibition explores the history of Gulf navigation.",
        "تاريخ الملاحة في الخليج",
        "Traditional dhow boats and maritime exhibits",
        [("Culture", "topic"), ("Gulf", "location")],
    ),
    (
        "تقرير اقتصادي يتناول فرص الاستثمار في البنية التحتية",
        "An economic report examines infrastructure investment opportunities.",
        "آفاق الاستثمار في البنية التحتية",
        "Aerial view of infrastructure and roads",
        [("Investment", "topic"), ("Kuwait", "location")],
    ),
]


def make_event(index, timestamp=None):
    timestamp = timestamp or utcnow()
    scenario = SCENARIOS[index % len(SCENARIOS)]
    ar, en, ocr, visual, entities = scenario
    channel = CHANNELS[index % len(CHANNELS)]
    return TDO(
        channel_id=channel["id"],
        start=timestamp - timedelta(seconds=6),
        end=timestamp,
        transcript=ar,
        translation=en,
        ocr=ocr,
        visual=visual,
        entities=[Entity(name=n, kind=k) for n, k in entities],
        speaker=f"{channel['id']}:speaker-{index % 2 + 1}",
        confidence=0.94,
        simulated=True,
        source="dira-simulator",
    )
