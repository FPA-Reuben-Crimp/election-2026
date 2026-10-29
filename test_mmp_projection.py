import unittest

from mmp_projection import project_mmp


class MmpProjectionTests(unittest.TestCase):
    def test_party_below_five_percent_qualifies_with_an_electorate_win(self):
        result = project_mmp(
            {"National": 49, "Labour": 49, "Te Pati Maori": 2},
            {"Te Pati Maori": 1},
        )

        maori = result["parties"]["Te Pati Maori"]
        self.assertTrue(maori["qualified"])
        self.assertEqual(maori["electorate_seats"], 1)
        self.assertGreater(maori["proportional_entitlement"], 0)
        self.assertEqual(maori["list_seats"], maori["proportional_entitlement"] - 1)

    def test_party_below_five_percent_without_electorate_win_is_excluded(self):
        result = project_mmp(
            {"National": 49, "Labour": 49, "Te Pati Maori": 2},
            {},
        )

        maori = result["parties"]["Te Pati Maori"]
        self.assertFalse(maori["qualified"])
        self.assertEqual(maori["total_seats"], 0)

    def test_electorate_seats_above_entitlement_create_overhang(self):
        result = project_mmp(
            {"National": 49, "Labour": 49, "Te Pati Maori": 2},
            {"Te Pati Maori": 4},
        )

        maori = result["parties"]["Te Pati Maori"]
        self.assertEqual(maori["proportional_entitlement"], 2)
        self.assertEqual(maori["overhang_seats"], 2)
        self.assertEqual(result["parliament_size"], 122)

    def test_latest_published_poll_reproduces_page_seat_allocation(self):
        result = project_mmp(
            {
                "National": 24.8,
                "Labour": 30.6,
                "Green": 14.5,
                "ACT": 10.1,
                "New Zealand First": 9.9,
                "Te Pati Maori": 1.9,
                "Opportunity": 7.2,
                "Other": 0.9,
            },
            {"Te Pati Maori": 4},
        )

        self.assertEqual(
            {
                party: values["proportional_entitlement"]
                for party, values in result["parties"].items()
                if values["proportional_entitlement"]
            },
            {
                "National": 30,
                "Labour": 37,
                "Green": 18,
                "ACT": 12,
                "New Zealand First": 12,
                "Te Pati Maori": 2,
                "Opportunity": 9,
            },
        )


if __name__ == "__main__":
    unittest.main()