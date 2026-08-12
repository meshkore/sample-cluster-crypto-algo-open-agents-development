"""System Three: the intraday system that learns instead of being told.

Beside System Four (`quantlab_trading`, daily, rule trees) and the intraday
momentum system (`quantlab_intraday`, 5m, hand-written rules). This one is fed
the same tape and the same 0.30% toll and is asked to find the rule itself.

Read `labels.py` and `splits.py` before anything else here. The modelling is the
easy part and the published base rate is discouraging -- gross edges that vanish
under costs, ROC-AUC 0.60 that cannot pay a toll. What separates a result from an
artefact in this subject is whether the label describes a trade someone could
take and whether the split hid the answer from the model, and both of those are
decided in those two files.
"""

FAMILY = "intraday-ml"
INTERVAL = "5m"
