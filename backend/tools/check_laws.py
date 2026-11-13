"""Which of the main Moroccan laws are in the installed pack?   py tools\\check_laws.py        (py tools\\check_laws.py missing  -> only what is missing)

FOUND = the law is in the pack (with its number of articles in force today).  IN CODE = an amending law whose articles are already inside a code.
MISSING = not found: download it (Adala / SGG) and install it.  A law is matched by its number inside the instrument id."""
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalrag.config import Settings  # noqa: E402

# (area, English name, [numbers in the instrument id], in_code check or None, Arabic title to search for)
LAWS = [
    # ---------------------------------------------------------------- constitution & organic laws
    ("Constitution / organic laws", "Constitution 2011", ["CONST_2011", "CONSTITUTION"], None, "دستور المملكة المغربية 2011"),
    ("Constitution / organic laws", "Regions 111.14", ["111.14"], None, "القانون التنظيمي رقم 111.14 المتعلق بالجهات"),
    ("Constitution / organic laws", "Provinces and prefectures 112.14", ["112.14"], None, "القانون التنظيمي رقم 112.14 المتعلق بالعمالات والأقاليم"),
    ("Constitution / organic laws", "Communes 113.14", ["113.14"], None, "القانون التنظيمي رقم 113.14 المتعلق بالجماعات"),
    ("Constitution / organic laws", "Finance Act organic law 130.13", ["130.13"], None, "القانون التنظيمي رقم 130.13 لقانون المالية"),
    ("Constitution / organic laws", "Government organisation 065.13", ["065.13", "65.13"], None, "القانون التنظيمي رقم 065.13 المتعلق بتنظيم وتسيير أشغال الحكومة"),
    ("Constitution / organic laws", "Appointment to senior posts 02.12", ["02.12"], None, "القانون التنظيمي رقم 02.12 المتعلق بالتعيين في المناصب العليا"),
    ("Constitution / organic laws", "House of Representatives 27.11", ["27.11"], None, "القانون التنظيمي رقم 27.11 المتعلق بمجلس النواب"),
    ("Constitution / organic laws", "House of Councillors 28.11", ["28.11"], None, "القانون التنظيمي رقم 28.11 المتعلق بمجلس المستشارين"),
    ("Constitution / organic laws", "Political parties 29.11", ["29.11"], None, "القانون التنظيمي رقم 29.11 المتعلق بالأحزاب السياسية"),
    ("Constitution / organic laws", "Election of territorial councils 59.11", ["59.11"], None, "القانون التنظيمي رقم 59.11 المتعلق بانتخاب أعضاء مجالس الجماعات الترابية"),
    ("Constitution / organic laws", "Electoral lists 57.11", ["57.11"], None, "القانون رقم 57.11 المتعلق باللوائح الانتخابية العامة"),
    ("Constitution / organic laws", "Electoral code 9.97", ["9.97"], None, "القانون رقم 9.97 المتعلق بمدونة الانتخابات"),
    ("Constitution / organic laws", "Constitutional Court 066.13", ["066.13", "66.13"], None, "القانون التنظيمي رقم 066.13 المتعلق بالمحكمة الدستورية"),
    ("Constitution / organic laws", "Superior Council of Judicial Power 100.13", ["100.13"], None, "القانون التنظيمي رقم 100.13 المتعلق بالمجلس الأعلى للسلطة القضائية"),
    ("Constitution / organic laws", "Statute of judges 106.13", ["106.13"], None, "القانون التنظيمي رقم 106.13 المتعلق بالنظام الأساسي للقضاة"),
    ("Constitution / organic laws", "Petitions 44.14", ["44.14"], None, "القانون التنظيمي رقم 44.14 المتعلق بتقديم العرائض إلى السلطات العمومية"),
    ("Constitution / organic laws", "Legislative motions 64.14", ["64.14"], None, "القانون التنظيمي رقم 64.14 المتعلق بتقديم الملتمسات في مجال التشريع"),
    ("Constitution / organic laws", "Official status of Amazigh 26.16", ["26.16"], None, "القانون التنظيمي رقم 26.16 المتعلق بتفعيل الطابع الرسمي للأمازيغية"),
    ("Constitution / organic laws", "National Council for Languages 04.16", ["04.16"], None, "القانون التنظيمي رقم 04.16 المتعلق بالمجلس الوطني للغات والثقافة المغربية"),
    ("Constitution / organic laws", "Right to strike 97.15", ["97.15"], None, "القانون التنظيمي رقم 97.15 بتحديد شروط وكيفيات ممارسة حق الإضراب"),
    ("Constitution / organic laws", "Economic, Social and Environmental Council 128.12", ["128.12"], None, "القانون التنظيمي رقم 128.12 المتعلق بالمجلس الاقتصادي والاجتماعي والبيئي"),
    ("Constitution / organic laws", "Parliamentary fact-finding committees 085.13", ["085.13", "85.13"], None, "القانون التنظيمي رقم 085.13 المتعلق بطريقة تسيير اللجان النيابية لتقصي الحقائق"),
    # ---------------------------------------------------------------- justice & legal professions
    ("Justice / professions", "Judicial organisation 38.15", ["38.15"], None, "القانون رقم 38.15 المتعلق بالتنظيم القضائي"),
    ("Justice / professions", "Administrative courts 41.90 (ended 2026-08-24, see 58.25)", ["41.90", "58.25"], None, "القانون رقم 41.90 المحدث بموجبه محاكم إدارية"),
    ("Justice / professions", "Admin. courts of appeal 80.03 (ended 2026-08-24, see 58.25)", ["80.03", "58.25"], None, "القانون رقم 80.03 المحدثة بموجبه محاكم استئناف إدارية"),
    ("Justice / professions", "Commercial courts 53.95 (ended 2026-08-24, see 58.25)", ["53.95", "58.25"], None, "القانون رقم 53.95 القاضي بإحداث محاكم تجارية"),
    ("Justice / professions", "Public prosecution presidency 33.17", ["33.17"], None, "القانون رقم 33.17 المتعلق بنقل اختصاصات السلطة الحكومية المكلفة بالعدل إلى الوكيل العام للملك لدى محكمة النقض"),
    ("Justice / professions", "Military justice code 108.13", ["108.13"], None, "القانون رقم 108.13 المتعلق بالقضاء العسكري"),
    ("Justice / professions", "Lawyers 28.08", ["28.08"], None, "القانون رقم 28.08 المتعلق بتنظيم مهنة المحاماة"),
    ("Justice / professions", "Professional civil companies of lawyers 29.08", ["29.08"], None, "القانون رقم 29.08 المتعلق بالشركات المدنية المهنية للمحاماة"),
    ("Justice / professions", "Adouls 16.03", ["16.03"], None, "القانون رقم 16.03 المتعلق بخطة العدالة"),
    ("Justice / professions", "Notaries 32.09", ["32.09"], None, "القانون رقم 32.09 المتعلق بتنظيم مهنة التوثيق"),
    ("Justice / professions", "Judicial officers (huissiers) 81.03", ["81.03"], None, "القانون رقم 81.03 بتنظيم مهنة المفوضين القضائيين"),
    ("Justice / professions", "Judicial experts 45.00", ["45.00"], None, "القانون رقم 45.00 المتعلق بالخبراء القضائيين"),
    ("Justice / professions", "Sworn translators 50.00", ["50.00"], None, "القانون رقم 50.00 المتعلق بالتراجمة المقبولين لدى المحاكم"),
    ("Justice / professions", "Arbitration and mediation 95.17", ["95.17"], None, "القانون رقم 95.17 المتعلق بالتحكيم والوساطة الاتفاقية"),
    ("Justice / professions", "National Human Rights Council 76.15", ["76.15"], None, "القانون رقم 76.15 المتعلق بإعادة تنظيم المجلس الوطني لحقوق الإنسان"),
    ("Justice / professions", "Ombudsman (Mediator) 14.16", ["14.16"], None, "القانون رقم 14.16 المتعلق بمؤسسة الوسيط"),
    ("Justice / professions", "Anti-corruption authority 46.19", ["46.19"], None, "القانون رقم 46.19 المتعلق بالهيئة الوطنية للنزاهة والوقاية من الرشوة ومحاربتها"),
    ("Justice / professions", "Competition Council 20.13", ["20.13"], None, "القانون رقم 20.13 المتعلق بمجلس المنافسة"),
    # ---------------------------------------------------------------- civil & property
    ("Civil / property", "Obligations and Contracts (DOC 1913)", ["DOC-1913", "DOC_1913"], None, "ظهير الالتزامات والعقود"),
    ("Civil / property", "Civil Procedure Code (1974 dahir, 58.25 from 2026)", ["1.74.447", "58.25"], None, "قانون المسطرة المدنية (ظهير 1.74.447)"),
    ("Civil / property", "Real rights code 39.08", ["39.08"], None, "القانون رقم 39.08 المتعلق بمدونة الحقوق العينية"),
    ("Civil / property", "Land registration (1913 dahir, law 14.07)", ["TF-1913", "14.07"], None, "ظهير التحفيظ العقاري كما غير بالقانون رقم 14.07"),
    ("Civil / property", "Habous (waqf) code 1.09.236", ["1.09.236"], None, "مدونة الأوقاف (ظهير 1.09.236)"),
    ("Civil / property", "Co-ownership 18.00", ["18.00"], None, "القانون رقم 18.00 المتعلق بنظام الملكية المشتركة للعقارات المبنية"),
    ("Civil / property", "Sale of buildings under construction 44.00", ["44.00"], ("DAHIR_DOC-1913", "618-1"), "القانون رقم 44.00 المتعلق ببيع العقارات في طور الإنجاز"),
    ("Civil / property", "Residential leases 67.12", ["67.12"], None, "القانون رقم 67.12 المتعلق بكراء المحلات المعدة للسكنى أو للاستعمال المهني"),
    ("Civil / property", "Commercial leases 49.16", ["49.16"], None, "القانون رقم 49.16 المتعلق بكراء العقارات أو المحلات المخصصة للاستعمال التجاري"),
    ("Civil / property", "Lease-ownership (ijara) 51.00", ["51.00"], None, "القانون رقم 51.00 المتعلق بالإيجار المفضي إلى تملك العقار"),
    ("Civil / property", "Movable securities 21.18", ["21.18"], None, "القانون رقم 21.18 المتعلق بالضمانات المنقولة"),
    ("Civil / property", "Expropriation 7.81", ["7.81"], None, "القانون رقم 7.81 المتعلق بنزع الملكية لأجل المنفعة العامة"),
    ("Civil / property", "Urban planning 12.90", ["12.90"], None, "القانون رقم 12.90 المتعلق بالتعمير"),
    ("Civil / property", "Subdivisions 25.90", ["25.90"], None, "القانون رقم 25.90 المتعلق بالتجزئات العقارية والمجموعات السكنية"),
    ("Civil / property", "Urban planning offences 66.12", ["66.12"], None, "القانون رقم 66.12 المتعلق بمراقبة وزجر المخالفات في مجال التعمير والبناء"),
    ("Civil / property", "Collective lands 62.17", ["62.17"], None, "القانون رقم 62.17 بشأن الوصاية الإدارية على الجماعات السلالية"),
    ("Civil / property", "Collective lands delimitation 63.17", ["63.17"], None, "القانون رقم 63.17 المتعلق بالتحديد الإداري لأراضي الجماعات السلالية"),
    ("Civil / property", "Copyright 2.00", ["2.00"], None, "القانون رقم 2.00 المتعلق بحقوق المؤلف والحقوق المجاورة"),
    ("Civil / property", "Industrial property 17.97", ["17.97"], None, "القانون رقم 17.97 المتعلق بحماية الملكية الصناعية"),
    # ---------------------------------------------------------------- criminal
    ("Criminal", "Penal Code (1963)", ["1.59.413"], None, "مجموعة القانون الجنائي"),
    ("Criminal", "Criminal Procedure 22.01", ["22.01"], None, "القانون رقم 22.01 المتعلق بالمسطرة الجنائية"),
    ("Criminal", "Violence against women 103.13", ["103.13"], None, "القانون رقم 103.13 المتعلق بمحاربة العنف ضد النساء"),
    ("Criminal", "Human trafficking 27.14", ["27.14"], ("DAHIR_1.59.413", "448-1"), "القانون رقم 27.14 المتعلق بمكافحة الاتجار بالبشر"),
    ("Criminal", "Terrorism 03.03", ["03.03"], ("DAHIR_1.59.413", "218-1"), "القانون رقم 03.03 المتعلق بمكافحة الإرهاب"),
    ("Criminal", "Cybercrime 07.03", ["07.03"], ("DAHIR_1.59.413", "607-3"), "القانون رقم 07.03 بتتميم مجموعة القانون الجنائي فيما يتعلق بالجرائم المتعلقة بنظم المعالجة الآلية للمعطيات"),
    ("Criminal", "Sports violence 09.09", ["09.09"], ("DAHIR_1.59.413", "308-1"), "القانون رقم 09.09 المتعلق بالعنف المرتكب أثناء المباريات أو التظاهرات الرياضية"),
    ("Criminal", "Witness and whistleblower protection 37.10", ["37.10"], ("LAW_22.01", "82-7"), "القانون رقم 37.10 المتعلق بحماية الضحايا والشهود والخبراء والمبلغين"),
    ("Criminal", "Money laundering 43.05", ["43.05"], None, "القانون رقم 43.05 المتعلق بمكافحة غسل الأموال"),
    ("Criminal", "Alternative sanctions 43.22", ["43.22"], None, "القانون رقم 43.22 المتعلق بالعقوبات البديلة"),
    ("Criminal", "Prisons 23.98", ["23.98"], None, "القانون رقم 23.98 المتعلق بتنظيم وتسيير المؤسسات السجنية"),
    ("Criminal", "Narcotics dahir 1.73.282", ["1.73.282"], None, "ظهير 1.73.282 بزجر الإدمان على المخدرات السامة"),
    ("Criminal", "Legal uses of cannabis 13.21", ["13.21"], None, "القانون رقم 13.21 المتعلق بالاستعمالات المشروعة للقنب الهندي"),
    ("Criminal", "Anti-doping in sport 97.12", ["97.12"], None, "القانون رقم 97.12 المتعلق بمكافحة تعاطي المنشطات في مجال الرياضة"),
    # ---------------------------------------------------------------- family & persons
    ("Family / persons", "Family Code 70.03", ["70.03"], None, "القانون رقم 70.03 بمثابة مدونة الأسرة"),
    ("Family / persons", "Civil status 37.99", ["37.99"], None, "القانون رقم 37.99 المتعلق بالحالة المدنية"),
    ("Family / persons", "Civil status decree 2.99.665", ["2.99.665"], None, "المرسوم رقم 2.99.665 لتطبيق القانون رقم 37.99"),
    ("Family / persons", "Kafala 15.01", ["15.01"], None, "القانون رقم 15.01 المتعلق بكفالة الأطفال المهملين"),
    ("Family / persons", "Family solidarity fund 41.10", ["41.10"], None, "القانون رقم 41.10 المتعلق بتحديد شروط ومساطر الاستفادة من صندوق التكافل العائلي"),
    ("Family / persons", "Social welfare institutions 65.15", ["65.15"], None, "القانون رقم 65.15 المتعلق بمؤسسات الرعاية الاجتماعية"),
    ("Family / persons", "Nationality Code (dahir 1.58.250)", ["1.58.250"], None, "قانون الجنسية المغربية (ظهير 1.58.250)"),
    ("Family / persons", "Foreigners entry and stay 02.03", ["02.03"], None, "القانون رقم 02.03 المتعلق بدخول وإقامة الأجانب بالمملكة المغربية"),
    ("Family / persons", "Rights of persons with disabilities 97.13", ["97.13"], None, "القانون الإطار رقم 97.13 المتعلق بحماية حقوق الأشخاص في وضعية إعاقة (الظهير 1.16.52)"),
    ("Family / persons", "National electronic ID card 04.20", ["04.20"], None, "القانون رقم 04.20 المتعلق بالبطاقة الوطنية للتعريف الإلكترونية"),
    ("Family / persons", "Associations (dahir 1.58.376)", ["1.58.376"], None, "ظهير 1.58.376 بتنظيم حق تأسيس الجمعيات"),
    ("Family / persons", "Public gatherings (dahir 1.58.377)", ["1.58.377"], None, "ظهير 1.58.377 بشأن التجمعات العمومية"),
    ("Family / persons", "Military service 44.18", ["44.18"], None, "القانون رقم 44.18 المتعلق بالخدمة العسكرية"),
    # ---------------------------------------------------------------- labour & social
    ("Labour / social", "Labour Code 65.99", ["65.99"], None, "القانون رقم 65.99 المتعلق بمدونة الشغل"),
    ("Labour / social", "Civil service statute (1958)", ["1.58.008"], None, "الظهير 1.58.008 بمثابة النظام الأساسي العام للوظيفة العمومية"),
    ("Labour / social", "Domestic workers 19.12", ["19.12"], None, "القانون رقم 19.12 المتعلق بالعاملات والعمال المنزليين"),
    ("Labour / social", "Social security (CNSS) 1.72.184", ["1.72.184"], None, "الظهير 1.72.184 المتعلق بنظام الضمان الاجتماعي"),
    ("Labour / social", "Job-loss allowance 03.14", ["03.14"], ("DAHIR_1.72.184_2025", "46-1"), "القانون رقم 03.14 المتعلق بالتعويض عن فقدان الشغل"),
    ("Labour / social", "Basic health coverage 65.00", ["65.00"], None, "القانون رقم 65.00 بمثابة مدونة التغطية الصحية الأساسية"),
    ("Labour / social", "Social protection framework 09.21", ["09.21"], None, "القانون الإطار رقم 09.21 المتعلق بالحماية الاجتماعية"),
    ("Labour / social", "Work accidents 18.12", ["18.12"], None, "القانون رقم 18.12 المتعلق بالتعويض عن حوادث الشغل"),
    ("Labour / social", "AMO for the self-employed 98.15", ["98.15"], None, "القانون رقم 98.15 المتعلق بالتأمين الإجباري الأساسي عن المرض الخاص بالمستقلين"),
    ("Labour / social", "Pensions for the self-employed 99.15", ["99.15"], None, "القانون رقم 99.15 بإحداث نظام للمعاشات لفائدة المستقلين"),
    ("Labour / social", "Civil pensions 011.71", ["011.71", "11.71"], None, "القانون رقم 011.71 المحدث بموجبه نظام للمعاشات المدنية"),
    ("Labour / social", "Military pensions 013.71", ["013.71", "13.71"], None, "القانون رقم 013.71 المحدث بموجبه نظام المعاشات العسكرية"),
    ("Labour / social", "RCAR pensions (dahir 1.77.216)", ["1.77.216"], None, "الظهير 1.77.216 بإحداث نظام جماعي لمنح رواتب التقاعد"),
    ("Labour / social", "Mutual societies (dahir 1.57.187)", ["1.57.187"], None, "الظهير 1.57.187 بسن نظام أساسي للتعاون المتبادل"),
    ("Labour / social", "Social registry / targeting 72.18", ["72.18"], None, "القانون رقم 72.18 المتعلق بمنظومة استهداف المستفيدين من برامج الدعم الاجتماعي"),
    # ---------------------------------------------------------------- business & finance
    ("Business / finance", "Commerce Code 15.95", ["15.95"], None, "القانون رقم 15.95 المتعلق بمدونة التجارة"),
    ("Business / finance", "Payment delays 49.15", ["49.15"], ("LAW_15.95", "78-2"), "القانون رقم 49.15 بشأن آجال الأداء (في مدونة التجارة)"),
    ("Business / finance", "Companies in difficulty 73.17", ["73.17"], ("LAW_15.95", "546"), "القانون رقم 73.17 المتعلق بمساطر صعوبات المقاولة"),
    ("Business / finance", "Public limited companies 17.95", ["17.95"], None, "القانون رقم 17.95 المتعلق بشركات المساهمة"),
    ("Business / finance", "SARL and partnerships 5.96", ["5.96"], None, "القانون رقم 5.96 المتعلق بشركة التضامن والتوصية والمسؤولية المحدودة والمحاصة"),
    ("Business / finance", "Economic interest groups 13.97", ["13.97"], None, "القانون رقم 13.97 المتعلق بمجموعات النفع الاقتصادي"),
    ("Business / finance", "Accounting obligations of traders 9.88", ["9.88"], None, "القانون رقم 9.88 المتعلق بالقواعد المحاسبية الواجب على التجار العمل بها"),
    ("Business / finance", "Chartered accountants 15.89", ["15.89"], None, "القانون رقم 15.89 المنظم لمهنة الخبرة المحاسبية"),
    ("Business / finance", "Cooperatives 112.12", ["112.12"], None, "القانون رقم 112.12 المتعلق بالتعاونيات"),
    ("Business / finance", "Auto-entrepreneur 114.13", ["114.13"], None, "القانون رقم 114.13 المتعلق بنظام المقاول الذاتي"),
    ("Business / finance", "Competition and prices 104.12", ["104.12"], None, "القانون رقم 104.12 المتعلق بحرية الأسعار والمنافسة"),
    ("Business / finance", "Consumer protection 31.08", ["31.08"], None, "القانون رقم 31.08 القاضي بتحديد تدابير لحماية المستهلك"),
    ("Business / finance", "Insurance code 17.99", ["17.99"], None, "القانون رقم 17.99 المتعلق بمدونة التأمينات"),
    ("Business / finance", "Credit institutions 103.12", ["103.12"], None, "القانون رقم 103.12 المتعلق بمؤسسات الائتمان والهيئات المعتبرة في حكمها"),
    ("Business / finance", "Bank Al-Maghrib statute 40.17", ["40.17"], None, "القانون رقم 40.17 المتعلق بالقانون الأساسي لبنك المغرب"),
    ("Business / finance", "Microfinance 50.20", ["50.20"], None, "القانون رقم 50.20 المتعلق بالتمويل التضامني"),
    ("Business / finance", "Capital market authority AMMC 43.12", ["43.12"], None, "القانون رقم 43.12 المتعلق بالهيئة المغربية لسوق الرساميل"),
    ("Business / finance", "Stock exchange 19.14", ["19.14"], None, "القانون رقم 19.14 المتعلق ببورصة القيم وشركات البورصة"),
    ("Business / finance", "Public offerings 44.12", ["44.12"], None, "القانون رقم 44.12 المتعلق بدعوة الجمهور إلى الاكتتاب"),
    ("Business / finance", "Collective investment (OPCVM) 03.25", ["03.25", "1.93.213"], None, "القانون رقم 03.25 المتعلق بهيئات التوظيف الجماعي للقيم المنقولة"),
    ("Business / finance", "Securitisation 33.06", ["33.06"], None, "القانون رقم 33.06 المتعلق بتسنيد الأصول"),
    ("Business / finance", "Crowdfunding 15.18", ["15.18"], None, "القانون رقم 15.18 المتعلق بالتمويل التعاوني"),
    ("Business / finance", "Investment charter 03.22", ["03.22"], None, "القانون الإطار رقم 03.22 بمثابة ميثاق الاستثمار"),
    ("Business / finance", "Regional investment centres 47.18", ["47.18"], None, "القانون رقم 47.18 المتعلق بإصلاح المراكز الجهوية للاستثمار"),
    ("Business / finance", "Export free zones 19.94", ["19.94"], None, "القانون رقم 19.94 المتعلق بمناطق التصدير الحرة"),
    ("Business / finance", "Foreign trade 91.14", ["91.14", "13.89"], None, "القانون رقم 91.14 المتعلق بالتجارة الخارجية"),
    ("Business / finance", "Public-private partnership 86.12", ["86.12"], None, "القانون رقم 86.12 المتعلق بعقود الشراكة بين القطاعين العام والخاص"),
    ("Business / finance", "Delegated management 54.05", ["54.05"], None, "القانون رقم 54.05 المتعلق بالتدبير المفوض للمرافق العامة"),
    ("Business / finance", "State control of public enterprises 69.00", ["69.00"], None, "القانون رقم 69.00 المتعلق بالمراقبة المالية للدولة على المنشآت العامة"),
    ("Business / finance", "Public enterprises reform 50.21", ["50.21"], None, "القانون الإطار رقم 50.21 المتعلق بإصلاح المؤسسات والمقاولات العمومية"),
    ("Business / finance", "Mohammed VI Investment Fund 76.20", ["76.20"], None, "القانون رقم 76.20 بإحداث صندوق محمد السادس للاستثمار"),
    ("Business / finance", "Mining 33.13", ["33.13"], None, "القانون رقم 33.13 المتعلق بالمناجم"),
    ("Business / finance", "Hydrocarbons 21.90", ["21.90"], None, "القانون رقم 21.90 المتعلق بالبحث عن الهيدروكاربورات واستغلالها"),
    ("Business / finance", "Renewable energy 13.09", ["13.09"], None, "القانون رقم 13.09 المتعلق بالطاقات المتجددة"),
    ("Business / finance", "Electricity self-production 82.21", ["82.21"], None, "القانون رقم 82.21 المتعلق بالإنتاج الذاتي للطاقة الكهربائية"),
    ("Business / finance", "Tourist establishments 80.14", ["80.14"], None, "القانون رقم 80.14 المتعلق بالمؤسسات السياحية وأشكال الإيواء السياحي الأخرى"),
    ("Business / finance", "Travel agencies 11.16", ["11.16", "31.96"], None, "القانون رقم 11.16 المتعلق بتنظيم مهنة وكيل الأسفار"),
    ("Business / finance", "Tourist guides 05.12", ["05.12"], None, "القانون رقم 05.12 المتعلق بالنظام الأساسي للمرشدين السياحيين"),
    # ---------------------------------------------------------------- tax & public finance
    ("Tax / public finance", "General Tax Code (2024)", ["CGI-2024"], None, "المدونة العامة للضرائب"),
    ("Tax / public finance", "Local taxation 47.06", ["47.06"], None, "القانون رقم 47.06 المتعلق بجبايات الجماعات المحلية"),
    ("Tax / public finance", "Recovery of public debts 15.97", ["15.97"], None, "القانون رقم 15.97 بمثابة مدونة تحصيل الديون العمومية"),
    ("Tax / public finance", "Customs code (dahir 1.77.339)", ["1.77.339"], None, "مدونة الجمارك والضرائب غير المباشرة (ظهير 1.77.339)"),
    ("Tax / public finance", "Consumption taxes (dahir 1.77.340)", ["1.77.340", "1309.77"], None, "الظهير 1.77.340 بشأن الضرائب الداخلية على الاستهلاك"),
    ("Tax / public finance", "Public procurement decree 2.22.431", ["2.22.431"], None, "المرسوم رقم 2.22.431 المتعلق بالصفقات العمومية"),
    ("Tax / public finance", "Financial courts code 62.99", ["62.99"], None, "القانون رقم 62.99 المتعلق بمدونة المحاكم المالية"),
    # ---------------------------------------------------------------- administration & digital
    ("Administration / digital", "Reasons for administrative decisions 01.03", ["01.03"], None, "القانون رقم 01.03 بشأن إلزام الإدارات بتعليل قراراتها الإدارية"),
    ("Administration / digital", "Access to information 31.13", ["31.13"], None, "القانون رقم 31.13 المتعلق بالحق في الحصول على المعلومات"),
    ("Administration / digital", "Charter of public services 54.19", ["54.19"], None, "القانون رقم 54.19 بمثابة ميثاق المرافق العمومية"),
    ("Administration / digital", "Simplification of procedures 55.19", ["55.19"], None, "القانون رقم 55.19 المتعلق بتبسيط المساطر والإجراءات الإدارية"),
    ("Administration / digital", "Archives 69.99", ["69.99"], None, "القانون رقم 69.99 المتعلق بالأرشيف"),
    ("Administration / digital", "Health state of emergency 2.20.292", ["2.20.292"], None, "المرسوم بقانون رقم 2.20.292 المتعلق بسن أحكام خاصة بحالة الطوارئ الصحية"),
    ("Administration / digital", "Personal data 09.08", ["09.08"], None, "القانون رقم 09.08 المتعلق بحماية الأشخاص الذاتيين تجاه معالجة المعطيات ذات الطابع الشخصي"),
    ("Administration / digital", "Electronic exchange of legal data 53.05", ["53.05"], None, "القانون رقم 53.05 المتعلق بالتبادل الإلكتروني للمعطيات القانونية"),
    ("Administration / digital", "Electronic trust services 43.20", ["43.20"], None, "القانون رقم 43.20 المتعلق بخدمات الثقة بشأن المعاملات الإلكترونية"),
    ("Administration / digital", "Cybersecurity 05.20", ["05.20"], None, "القانون رقم 05.20 المتعلق بالأمن السيبراني"),
    ("Administration / digital", "Telecommunications 24.96", ["24.96"], None, "القانون رقم 24.96 المتعلق بالبريد والمواصلات"),
    # ---------------------------------------------------------------- other sectors
    ("Other sectors", "Press and publishing 88.13", ["88.13"], None, "القانون رقم 88.13 المتعلق بالصحافة والنشر"),
    ("Other sectors", "Professional journalists 89.13", ["89.13"], None, "القانون رقم 89.13 المتعلق بالنظام الأساسي للصحفيين المهنيين"),
    ("Other sectors", "National press council 90.13", ["90.13"], None, "القانون رقم 90.13 القاضي بإحداث المجلس الوطني للصحافة"),
    ("Other sectors", "Audiovisual communication 77.03", ["77.03"], None, "القانون رقم 77.03 المتعلق بالاتصال السمعي البصري"),
    ("Other sectors", "Cinema industry 18.23", ["18.23", "20.99"], None, "القانون رقم 18.23 المتعلق بالصناعة السينمائية وبإعادة تنظيم المركز السينمائي المغربي"),
    ("Other sectors", "Statute of the artist 68.16", ["68.16"], None, "القانون رقم 68.16 المتعلق بالفنان والمهن الفنية"),
    ("Other sectors", "Practice of medicine 131.13", ["131.13"], None, "القانون رقم 131.13 المتعلق بمزاولة مهنة الطب"),
    ("Other sectors", "Medicines and pharmacy 17.04", ["17.04"], None, "القانون رقم 17.04 بمثابة مدونة الأدوية والصيدلة"),
    ("Other sectors", "Medical biology labs 12.01", ["12.01"], None, "القانون رقم 12.01 المتعلق بالمختبرات الخاصة للتحاليل البيولوجية الطبية"),
    ("Other sectors", "Nursing professions 43.13", ["43.13"], None, "القانون رقم 43.13 المتعلق بمزاولة مهن التمريض"),
    ("Other sectors", "Rehabilitation professions 45.13", ["45.13"], None, "القانون رقم 45.13 المتعلق بمزاولة مهن الترويض وإعادة التأهيل"),
    ("Other sectors", "Organ donation 16.98", ["16.98"], None, "القانون رقم 16.98 المتعلق بالتبرع بالأعضاء والأنسجة البشرية"),
    ("Other sectors", "Medically assisted procreation 47.14", ["47.14"], None, "القانون رقم 47.14 المتعلق بالمساعدة الطبية على الإنجاب"),
    ("Other sectors", "Health system framework 34.09", ["34.09"], None, "القانون الإطار رقم 34.09 المتعلق بالمنظومة الصحية"),
    ("Other sectors", "Food safety 28.07", ["28.07"], None, "القانون رقم 28.07 المتعلق بالسلامة الصحية للمنتجات الغذائية"),
    ("Other sectors", "Education framework 51.17", ["51.17"], None, "القانون الإطار رقم 51.17 المتعلق بمنظومة التربية والتكوين"),
    ("Other sectors", "Higher education 01.00", ["01.00"], None, "القانون رقم 01.00 المتعلق بتنظيم التعليم العالي"),
    ("Other sectors", "Private schools 06.00", ["06.00"], None, "القانون رقم 06.00 بمثابة النظام الأساسي للتعليم المدرسي الخصوصي"),
    ("Other sectors", "Sport 30.09", ["30.09"], None, "القانون رقم 30.09 المتعلق بالتربية البدنية والرياضة"),
    ("Other sectors", "Water 36.15", ["36.15"], None, "القانون رقم 36.15 المتعلق بالماء"),
    ("Other sectors", "Environment protection 11.03", ["11.03"], None, "القانون رقم 11.03 المتعلق بحماية واستصلاح البيئة"),
    ("Other sectors", "Environmental impact studies 12.03", ["12.03"], None, "القانون رقم 12.03 المتعلق بدراسات التأثير على البيئة"),
    ("Other sectors", "Environment charter 99.12", ["99.12"], None, "القانون الإطار رقم 99.12 بمثابة ميثاق وطني للبيئة والتنمية المستدامة"),
    ("Other sectors", "Air pollution 13.03", ["13.03"], None, "القانون رقم 13.03 المتعلق بمكافحة تلوث الهواء"),
    ("Other sectors", "Coastline 81.12", ["81.12"], None, "القانون رقم 81.12 المتعلق بالساحل"),
    ("Other sectors", "Protected areas 22.07", ["22.07"], None, "القانون رقم 22.07 المتعلق بالمناطق المحمية"),
    ("Other sectors", "Plastic bags ban 77.15", ["77.15"], None, "القانون رقم 77.15 القاضي بمنع صنع الأكياس من مادة البلاستيك"),
    ("Other sectors", "Waste management 28.00", ["28.00"], None, "القانون رقم 28.00 المتعلق بتدبير النفايات والتخلص منها"),
    ("Other sectors", "Agricultural aggregation 04.12", ["04.12"], None, "القانون رقم 04.12 المتعلق بالتجميع الفلاحي"),
    ("Other sectors", "Sea fishing (dahir 1.73.255)", ["1.73.255"], None, "الظهير 1.73.255 المنظم للصيد البحري"),
    ("Other sectors", "Road traffic code 52.05", ["52.05"], None, "القانون رقم 52.05 المتعلق بمدونة السير على الطرق"),
    ("Other sectors", "Civil aviation code 40.13", ["40.13"], None, "القانون رقم 40.13 المتعلق بمدونة الطيران المدني"),
    ("Other sectors", "Cultural heritage 22.80", ["22.80"], None, "القانون رقم 22.80 المتعلق بالمحافظة على المباني التاريخية والمناظر"),
]

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Arabic titles in the Windows console
except Exception:
    pass
only_missing = len(sys.argv) > 1 and sys.argv[1].lower().startswith("miss")
today = date.today().isoformat()
db = sqlite3.connect(f"file:{Settings().resolved_lawpack_path()}?mode=ro", uri=True)
inst = db.execute(
    "SELECT i.instrument_id, (SELECT COUNT(*) FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id "
    "WHERE p.instrument_id=i.instrument_id AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?)), COALESCE(i.title_ar, '') "
    "FROM instrument i WHERE i.instrument_id NOT LIKE 'MA_BOCT_%'", (today, today)).fetchall()
titles = {iid: t for iid, n, t in inst if n > 0}
inst = [(iid, n) for iid, n, t in inst if n > 0]          # hidden / ended texts do not count


def promulgated_in(n: str) -> list[tuple[str, int]]:
    """A text read from a Bulletin Officiel issue is filed under the dahir that promulgates it ("ظهير شريف رقم 1.20.06 ... بتنفيذ القانون
    رقم 55.19"): its title names the law.  An amending text ("بتغيير القانون رقم ...") is not the law itself and does not count."""
    if not re.fullmatch(r"\d+\.\d+", n):
        return []
    pat = re.compile(r"بتنفيذ\s+(?:ال)?قانون(?:\s+التنظيمي|\s+الإطار|-الإطار)?\s+رقم\s*" + re.escape(n) + r"(?![\d.])")
    return [(iid, k) for iid, k in inst if pat.search(titles.get(iid, ""))]


def has(iid: str, n: str) -> bool:  # the number as a whole: 31.13 must not match 131.13, nor 25.90 match 2.25.90
    return re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", iid, re.I) is not None


def in_code(iid: str, art: str) -> bool:
    return db.execute("SELECT 1 FROM provision WHERE instrument_id=? AND (number=? OR provision_id LIKE ?) LIMIT 1",
                      (iid, art, f"%_ART_{art}")).fetchone() is not None


counts = {"FOUND": 0, "IN CODE": 0, "MISSING": 0}
area = ""
for a, name, needles, code, ar in LAWS:
    hits = sorted([r for r in inst if any(has(r[0], n) for n in needles)], key=lambda r: (not r[0].startswith(("LAW_", "ORG_", "CONST_", "DAHIR_", "DECREE_")), -r[1]))
    bo_hits = [] if hits else sorted({h for n in needles for h in promulgated_in(n)}, key=lambda r: -r[1])
    if hits:
        state, extra = "FOUND", f"{hits[0][1]:5} articles  ({hits[0][0]})"
    elif bo_hits:
        state, extra = "FOUND", f"{bo_hits[0][1]:5} articles  ({bo_hits[0][0]}, read from the Bulletin Officiel)"
    elif code and in_code(*code):
        state, extra = "IN CODE", f"its articles are inside {code[0]} (e.g. {code[1]})"
    else:
        state, extra = "MISSING", ""
    counts[state] += 1
    if only_missing and state != "MISSING":
        continue
    if a != area:
        print(f"\n{a}")
        area = a
    print(f"  {state:8} {name:52} {extra}" + (f"\n           ابحث عن: {ar}" if state == "MISSING" else ""))
print(f"\n{counts['FOUND']} found, {counts['IN CODE']} inside a code, {counts['MISSING']} missing  (of {len(LAWS)}).")
print("Law numbers in this list are from memory: if a law shows MISSING but you know it is installed, check its number.")
