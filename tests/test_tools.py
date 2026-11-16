import json
import unittest
from decimal import Decimal

from keren.access import AccessDenied, AuthorizedCustomer, authorize
from keren.tools import (MissingPriceError, Store, compute_valuation, exposure_check,
                         get_portfolio, get_prices, quarterly_fee_estimate)


class SpyStore(Store):
    reads = 0

    def portfolio(self, customer_id):
        SpyStore.reads += 1
        return super().portfolio(customer_id)


def run(store=None):
    store = store or Store()
    auth = authorize("demo-pm", "C-1042")
    pf = get_portfolio(store, auth)
    priced = get_prices(store, [h["asset"] for h in pf["holdings"]])
    return pf, priced


class ReferenceNumbers(unittest.TestCase):
    def setUp(self):
        pf, priced = run()
        self.val = compute_valuation(pf, priced)

    def test_total_and_positions(self):
        self.assertEqual(self.val["totalUsd"], "104510.00")
        vals = {p["asset"]: p["valueUsd"] for p in self.val["positions"]}
        self.assertEqual(vals, {"BTC": "53550.00", "ETH": "35960.00", "USDC": "15000.00"})

    def test_exposure_below_limit(self):
        chk = exposure_check(self.val)
        self.assertEqual((chk["asset"], chk["exposurePct"]), ("BTC", "51.2391"))
        self.assertFalse(chk["breach"])

    def test_fee_estimate_and_caveat(self):
        fee = quarterly_fee_estimate(self.val)
        self.assertEqual(fee["estimateUsd"], "209.02")
        self.assertIn("not a guaranteed", fee["assumption"])

    def test_cost_basis_is_historical(self):
        btc = self.val["positions"][0]
        self.assertEqual(btc["costBasisUsd"], "35020.00")
        self.assertIsNone(self.val["priceTimestamp"])

    def test_outputs_json_serializable_and_no_floats(self):
        pf, priced = run()
        for obj in (pf, priced, self.val, exposure_check(self.val), quarterly_fee_estimate(self.val)):
            json.dumps(obj)
        self.assertNotIn("float", json.dumps(self.val))
        Decimal(self.val["totalUsd"])


class FailSafe(unittest.TestCase):
    def test_missing_price_raises(self):
        store = Store(prices={"prices": {"BTC": "63000", "USDC": "1"}, "priceTimestamp": None})
        pf, priced = run(store)
        self.assertEqual(priced["missing"], ["ETH"])
        with self.assertRaises(MissingPriceError) as cm:
            compute_valuation(pf, priced)
        self.assertEqual(cm.exception.assets, ["ETH"])

    def test_null_price_counts_as_missing(self):
        store = Store(prices={"prices": {"BTC": "63000", "ETH": None, "USDC": "1"}})
        _, priced = run(store)
        self.assertEqual(priced["missing"], ["ETH"])


class Access(unittest.TestCase):
    def test_denied_before_any_data_access(self):
        SpyStore.reads = 0
        for op, cid in [("demo-pm", "C-2000"), ("demo-pm", "C-1042 OR 1=1"), ("demo-pm", ""),
                        ("demo-pm", None), ("intruder", "C-1042"), ("", "C-1042")]:
            with self.assertRaises(AccessDenied):
                authorize(op, cid)
        self.assertEqual(SpyStore.reads, 0)

    def test_identical_message_for_unknown_and_unauthorized(self):
        msgs = set()
        for op, cid in [("demo-pm", "C-2000"), ("intruder", "C-1042")]:
            try:
                authorize(op, cid)
            except AccessDenied as e:
                msgs.add(str(e))
        self.assertEqual(len(msgs), 1)

    def test_authorized_ok(self):
        self.assertEqual(authorize("demo-pm", " C-1042 "), AuthorizedCustomer("demo-pm", "C-1042"))


if __name__ == "__main__":
    unittest.main()
