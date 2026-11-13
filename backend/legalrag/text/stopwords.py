"""Small stopword sets (normalised forms) used only to build keyword queries."""

FR = set(
    "le la les l un une des du de d et en au aux a ou où que qui quoi dont ce ces cet cette est sont etre ete par pour sur sous dans avec sans "
    "se sa son ses leur leurs il elle ils elles je tu nous vous on ne pas plus mon ma mes ton ta tes comment quel quelle quels quelles puis-je peut peux dois doit "
    "si afin ainsi alors aussi".split()
)
EN = set(
    "the a an of to in on at for from by with without and or not is are was were be been what which who whom how can could should would may might "
    "i you we they he she it my your our their this that these those do does did if then than as about into over under".split()
)
AR = set(
    "في من الى إلى على عن مع او أو ان أن إن لا ما هو هي هم هذا هذه ذلك تلك الذي التي الذين كان كانت يكون تكون هل كيف متى اين أين لماذا ماذا بعد قبل عند حتى ثم قد لقد "
    "أي اي يمكن يمكنني و ب ل ك ف".split()
)
DARIJA = set("واش كيفاش علاش فين شحال باش ديال ديالي بغيت كاين ماشي دابا فاش اش شنو".split())

ALL = FR | EN | AR | DARIJA
# the tokens are compared after normalisation (ى->ي, ة->ه, أ/إ->ا): the stopwords must be too, or "متى" / "إلى" never matched "متي" / "الي"
from .arabic import normalize as _normalize  # noqa: E402

ALL = ALL | {_normalize(w) for w in ALL}
