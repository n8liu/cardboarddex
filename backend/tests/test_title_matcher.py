from decimal import Decimal
import pytest

from parsers.title_matcher import (
    RejectionReason,
    extract_grade_from_title,
    extract_numbers_from_title,
    extract_printing_from_title,
    normalize_card_number,
    parse_ebay_title,
)


class TestNegativeKeywordRejections:
    """Test that all fakes, merchandise, lots, foreign cards, and noise are strictly rejected."""

    def test_rejects_proxy_and_fake_cards(self) -> None:
        titles = [
            "Charizard PSA 10 proxy",
            "1999 Pokemon Base Set Charizard 4/102 Holo PSA 10 Custom Replica",
            "Charizard Base Set 1st Edition Fan Art Reproduction Proxy",
            "Pokemon Charizard Base Set Gold Metal Custom Card PSA 10",
            "Charizard 4/102 Orica Bootleg Replica",
            "Charizard Base Set Reprint Handmade",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject proxy title: {title}"
            assert result.rejection_reason == RejectionReason.PROXY_OR_FAKE.value

    def test_rejects_sealed_merchandise_and_boxes(self) -> None:
        titles = [
            "Pokemon 1999 Base Set Booster Pack Charizard Art PSA 10",
            "1999 Pokemon Base Set Empty Booster Box Charizard Artwork",
            "Pokemon Celebrations Charizard Elite Trainer Box ETB Sealed",
            "Charizard Tin Empty Display Only",
            "Pokemon Charizard Ultra Premium Collection UPC Sealed Case",
            "Charizard Slab Stand Display Only (No Card)",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject merchandise title: {title}"
            assert result.rejection_reason == RejectionReason.MERCHANDISE_OR_SEALED.value

    def test_rejects_lots_and_bundles(self) -> None:
        titles = [
            "Pokemon Card Lot including Charizard Holo 4/102",
            "Charizard Base Set + 50 Card Bulk Bundle",
            "Vintage Pokemon Collection Lot WOTC Charizard Blastoise",
            "Charizard Base Set Mystery Box Pack",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject lot title: {title}"
            assert result.rejection_reason == RejectionReason.LOT_OR_BUNDLE.value

    def test_rejects_digital_and_code_cards(self) -> None:
        titles = [
            "Charizard ex 151 Digital PTCGL Code Card",
            "Pokemon TCG Live Code Charizard Ultra Rare",
            "Charizard TCGO Online Code Instant Delivery",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject digital title: {title}"
            assert result.rejection_reason == RejectionReason.DIGITAL_OR_CODE.value

    def test_rejects_foreign_language_for_english_cards(self) -> None:
        titles = [
            "Japanese 1996 Pokemon Base Set Charizard Holo No.006 PSA 10",
            "Pokemon Charizard Base Set German Glurak 4/102 PSA 9",
            "French Dracaufeu 4/102 Base Set Holo PSA 8",
            "Korean Charizard Base Set 4/102 Holo",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set", is_target_japanese=False)
            assert result.status == "rejected", f"Failed to reject foreign title: {title}"
            assert result.rejection_reason == RejectionReason.FOREIGN_LANGUAGE.value

    def test_rejects_altered_and_autographed_cards(self) -> None:
        titles = [
            "Charizard 4/102 Base Set Mitsuhiro Arita Signed Autograph PSA 10",
            "Pokemon Charizard Extended Art Custom Painted 4/102",
            "Charizard Holo Hand Signed Auto Beckett",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject altered title: {title}"
            assert result.rejection_reason == RejectionReason.ALTERED_OR_AUTOGRAPH.value

    def test_rejects_grade_hype_and_speculative_titles(self) -> None:
        titles = [
            "1999 Pokemon Base Set Charizard 4/102 Holo PSA 10? Mint Rare",
            "Charizard Base Set 4/102 Near Mint - PSA 10 Candidate??",
            "Pokemon Charizard Holo 4/102 PSA Ready Gradeable!",
            "Charizard Base Set Mint Possible PSA 10",
            "Charizard Holo Base Set Gem Mint? Looks like PSA 10",
        ]
        for title in titles:
            result = parse_ebay_title(title, "Charizard", "4", "Base Set")
            assert result.status == "rejected", f"Failed to reject grade hype title: {title}"
            assert result.rejection_reason == RejectionReason.GRADE_HYPE_OR_UNCERTAIN.value


class TestIdentityMatching:
    """Test exact card number, name, and set identity verification."""

    def test_rejects_conflicting_card_number(self) -> None:
        # Title is for Blastoise #2/102 or Venusaur #15/102 but target is Charizard #4
        title = "1999 Pokemon Base Set Blastoise 2/102 Holo Rare PSA 10"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "rejected"

    def test_rejects_conflicting_number_in_same_set(self) -> None:
        # Title has Charizard with different number e.g. promo or secret rare
        title = "Pokemon Charizard VMAX Secret Rare #074/073 Champions Path PSA 10"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "rejected"
        assert result.rejection_reason in (
            RejectionReason.CARD_NUMBER_MISMATCH.value,
            RejectionReason.CARD_NAME_MISMATCH.value,
        )

    def test_rejects_prefix_variant_mismatch(self) -> None:
        # Target is regular "Charizard", title is "Dark Charizard" or "Shining Charizard"
        dark_title = "2000 Pokemon Team Rocket Dark Charizard Holo 4/82 PSA 10"
        result_dark = parse_ebay_title(dark_title, "Charizard", "4", "Base Set")
        assert result_dark.status == "rejected"
        assert result_dark.rejection_reason == RejectionReason.CARD_NAME_MISMATCH.value

        shining_title = "2001 Pokemon Neo Destiny Shining Charizard 107/105 1st Edition PSA 10"
        result_shining = parse_ebay_title(shining_title, "Charizard", "4", "Base Set")
        assert result_shining.status == "rejected"


class TestGradedSlabParsing:
    """Test valid graded slabs across all major grading companies (PSA, BGS, CGC, SGC)."""

    def test_psa_10_gem_mint(self) -> None:
        title = "1999 Pokemon Charizard Base Set Unlimited Holo Rare #4 PSA 10 Gem Mint"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "PSA"
        assert result.grade == Decimal("10.0")
        assert result.printing == "Unlimited"

    def test_psa_9_mint(self) -> None:
        title = "1999 Pokemon Base Set Charizard 4/102 Holo Rare PSA 9 MINT"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "PSA"
        assert result.grade == Decimal("9.0")

    def test_psa_8_5_half_grade(self) -> None:
        title = "Pokemon Base Set 1st Edition Charizard 4/102 PSA 8.5 NM-MT+"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "PSA"
        assert result.grade == Decimal("8.5")
        assert result.printing == "1st Edition"

    def test_psa_authentic(self) -> None:
        title = "1999 Pokemon Base Set Charizard 4/102 Holo PSA Authentic"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "PSA"
        assert result.grade is None

    def test_bgs_beckett_9_5_gem_mint(self) -> None:
        title = "2000 Pokemon Neo Genesis Lugia Holo #9 BGS 9.5 Gem Mint (Beckett)"
        result = parse_ebay_title(title, "Lugia", "9", "Neo Genesis")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "BGS"
        assert result.grade == Decimal("9.5")

    def test_bgs_10_pristine(self) -> None:
        title = "Pokemon Base Set Charizard 4/102 BGS 10 Pristine"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "BGS"
        assert result.grade == Decimal("10.0")

    def test_cgc_10_pristine(self) -> None:
        title = "2023 Pokemon 151 Charizard ex Special Illustration Rare 199/165 CGC 10 Pristine"
        result = parse_ebay_title(title, "Charizard ex", "199", "151")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "CGC"
        assert result.grade == Decimal("10.0")

    def test_cgc_9_5(self) -> None:
        title = "Pokemon Base Set Charizard 4/102 CGC 9.5 Gem Mint"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is True
        assert result.grading_company == "CGC"
        assert result.grade == Decimal("9.5")

    def test_sgc_10_and_old_scale(self) -> None:
        title_new = "Pokemon Base Set Charizard 4/102 SGC 10 Gem Mint"
        result_new = parse_ebay_title(title_new, "Charizard", "4", "Base Set")
        assert result_new.status == "matched"
        assert result_new.is_graded is True
        assert result_new.grading_company == "SGC"
        assert result_new.grade == Decimal("10.0")

        title_old = "Pokemon Base Set Charizard 4/102 SGC 98 Gem Mint"
        result_old = parse_ebay_title(title_old, "Charizard", "4", "Base Set")
        assert result_old.status == "matched"
        assert result_old.is_graded is True
        assert result_old.grading_company == "SGC"
        assert result_old.grade == Decimal("10.0")


class TestRawCardParsing:
    """Test valid raw card matching and condition extraction."""

    def test_raw_near_mint_card(self) -> None:
        title = "1999 Pokemon Base Set Charizard 4/102 Holo Rare Near Mint (NM)"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is False
        assert result.condition == "Near Mint"
        assert result.printing == "Holofoil"

    def test_raw_lightly_played_shadowless(self) -> None:
        title = "1999 Pokemon Base Set Shadowless Charizard 4/102 Holo LP Lightly Played"
        result = parse_ebay_title(title, "Charizard", "4", "Base Set")
        assert result.status == "matched"
        assert result.is_graded is False
        assert result.condition == "Lightly Played"
        assert result.printing == "Shadowless"

    def test_raw_reverse_holo(self) -> None:
        title = "2002 Legendary Collection Charizard 3/110 Reverse Holo Foil NM"
        result = parse_ebay_title(title, "Charizard", "3", "Legendary Collection")
        assert result.status == "matched"
        assert result.is_graded is False
        assert result.condition == "Near Mint"
        assert result.printing == "Reverse Holofoil"


class TestHelperUtilities:
    """Test helper parsing functions."""

    def test_normalize_card_number(self) -> None:
        assert normalize_card_number("004/102") == "4"
        assert normalize_card_number("#004") == "4"
        assert normalize_card_number("4") == "4"
        assert normalize_card_number("GG36/GG70") == "gg36"
        assert normalize_card_number("SWSH050") == "swsh050"

    def test_extract_numbers_from_title(self) -> None:
        assert "4" in extract_numbers_from_title("Charizard 4/102 Base Set Holo")
        assert "4" in extract_numbers_from_title("Charizard #004 Base Set")
        assert "swsh050" in extract_numbers_from_title("Charizard V Promo SWSH050 Sealed")
        assert "gg36" in extract_numbers_from_title("Entei V GG36/GG70 Crown Zenith")


class TestSealedProductTitleMatching:
    """Test sealed product title parsing, case isolation, and noise rejections."""

    def test_matches_valid_sealed_binder_collection(self) -> None:
        title = "Pokémon Scarlet & Violet 151 Binder Collection Factory Sealed"
        result = parse_ebay_title(
            title,
            target_card_name="151 Binder Collection",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert result.status == "matched"
        assert result.condition == "Sealed"
        assert result.printing == "Sealed"
        assert result.is_graded is False

    def test_matches_valid_sealed_case(self) -> None:
        title = "Pokémon Scarlet & Violet 151 Binder Collection Case Factory Sealed 6ct"
        result = parse_ebay_title(
            title,
            target_card_name="151 Binder Collection Case",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert result.status == "matched"
        assert result.condition == "Sealed"

    def test_case_mismatch_rejections(self) -> None:
        # 1. Target is a Case, but title is a single unit
        single_title = "Pokémon Scarlet & Violet 151 Binder Collection Factory Sealed"
        res1 = parse_ebay_title(
            single_title,
            target_card_name="151 Binder Collection Case",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res1.status == "rejected"
        assert res1.rejection_reason == RejectionReason.CASE_MISMATCH.value

        # 2. Target is a single unit, but title is a Case
        case_title = "Pokémon Scarlet & Violet 151 Binder Collection 6 Box Case Sealed"
        res2 = parse_ebay_title(
            case_title,
            target_card_name="151 Binder Collection",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res2.status == "rejected"
        assert res2.rejection_reason == RejectionReason.CASE_MISMATCH.value

    def test_empty_and_opened_sealed_rejections(self) -> None:
        noise_titles = [
            "Pokémon Scarlet & Violet 151 binder collection EMPTY BOX",
            "151 Binder Collection Open Box No Boosters",
            "151 Binder Collection Binder Only No Packs",
            "Pokemon 151 Booster Bundle Empty Box Display Only",
            "Scarlet & Violet 151 Elite Trainer Box ETB Box Only",
        ]
        for title in noise_titles:
            result = parse_ebay_title(
                title,
                target_card_name="151 Binder Collection",
                target_card_number="",
                target_set_name="SV: Scarlet & Violet 151",
                is_target_sealed=True,
            )
            assert result.status == "rejected", f"Failed to reject empty/opened title: {title}"
            assert result.rejection_reason == RejectionReason.EMPTY_OR_OPENED.value

    def test_foreign_language_rejection_for_sealed(self) -> None:
        title = "Pokemon 151 Binder Collection Brand New Sealed Box Scarlet & Violet *Spanish*"
        result = parse_ebay_title(
            title,
            target_card_name="151 Binder Collection",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert result.status == "rejected"
        assert result.rejection_reason == RejectionReason.FOREIGN_LANGUAGE.value

    def test_single_promo_card_extraction_rejection(self) -> None:
        titles = [
            "Pokemon 151 Binder Collection Snorlax Promo Card Holo #051",
            "Mew ex 199/165 Ultra Premium Collection 151",
            "Charizard ex 151 UPC Promo Card Only Sealed",
        ]
        for title in titles:
            result = parse_ebay_title(
                title,
                target_card_name="151 Binder Collection",
                target_card_number="",
                target_set_name="SV: Scarlet & Violet 151",
                is_target_sealed=True,
            )
            assert result.status == "rejected", f"Failed to reject promo card title: {title}"
            assert result.rejection_reason == RejectionReason.CARD_NAME_MISMATCH.value

    def test_booster_box_and_bundle_matching(self) -> None:
        # Bundle match
        bundle_title = "Pokemon Scarlet & Violet 151 Booster Bundle New Sealed"
        res_bundle = parse_ebay_title(
            bundle_title,
            target_card_name="151 Booster Bundle",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res_bundle.status == "matched"

        # Pack mismatch
        pack_title = "Pokemon Scarlet & Violet 151 Single Booster Pack"
        res_pack = parse_ebay_title(
            pack_title,
            target_card_name="151 Booster Bundle",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res_pack.status == "rejected"
        assert res_pack.rejection_reason == RejectionReason.PRODUCT_TYPE_MISMATCH.value

    def test_etb_pc_differentiation(self) -> None:
        # Standard ETB target matching standard ETB title
        standard_title = "Pokemon Scarlet & Violet 151 Elite Trainer Box ETB Sealed"
        res_std = parse_ebay_title(
            standard_title,
            target_card_name="151 Elite Trainer Box",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res_std.status == "matched"

        # Standard ETB target rejecting Pokemon Center ETB title
        pc_title = "Pokemon Scarlet & Violet 151 Pokemon Center Elite Trainer Box Sealed"
        res_pc_reject = parse_ebay_title(
            pc_title,
            target_card_name="151 Elite Trainer Box",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res_pc_reject.status == "rejected"
        assert res_pc_reject.rejection_reason == RejectionReason.PRODUCT_TYPE_MISMATCH.value

        # PC ETB target matching Pokemon Center ETB title
        res_pc_match = parse_ebay_title(
            pc_title,
            target_card_name="151 Pokemon Center Elite Trainer Box",
            target_card_number="",
            target_set_name="SV: Scarlet & Violet 151",
            is_target_sealed=True,
        )
        assert res_pc_match.status == "matched"

    def test_japanese_card_matching_permits_japanese_keywords(self) -> None:
        titles = [
            "Pokemon Card 151 Ivysaur AR 167/165 Japanese PSA 10",
            "Japanese 2023 Pokemon 151 Ivysaur 167/165 AR NM",
            "Pokemon Card Ivysaur AR 167/165 SV2a JPN Mint",
            "Ivysaur 167/165 SV2a Japan Pokemon Card 151",
        ]
        for title in titles:
            result = parse_ebay_title(
                title,
                target_card_name="Ivysaur - 167/165",
                target_card_number="167",
                target_set_name="SV2a: Pokemon Card 151",
                is_target_japanese=True,
            )
            assert result.status == "matched", f"Failed to match Japanese title: {title}, reason: {result.rejection_reason}"

    def test_japanese_card_rejects_other_foreign_languages(self) -> None:
        titles = [
            "Pokemon Ivysaur 167/165 German Bisaknosp PSA 9",
            "French Herbizarre 167/165 SV2a Holo",
            "Korean Ivysaur 167/165 Pokemon Card",
            "Pokemon Ivysaur Chinese 167/165 AR",
        ]
        for title in titles:
            result = parse_ebay_title(
                title,
                target_card_name="Ivysaur - 167/165",
                target_card_number="167",
                target_set_name="SV2a: Pokemon Card 151",
                is_target_japanese=True,
            )
            assert result.status == "rejected", f"Expected foreign rejection for: {title}"
            assert result.rejection_reason == RejectionReason.FOREIGN_LANGUAGE.value

    def test_master_ball_pattern_variant_matching(self) -> None:
        # Title without word "pattern" should match Master Ball target
        mb_title = "Pokemon Card 151 Ivysaur 002/165 Master Ball Reverse Holo PSA 10"
        res_mb = parse_ebay_title(
            mb_title,
            target_card_name="Ivysaur - 002/165 (Master Ball Pattern)",
            target_card_number="002",
            target_set_name="SV2a: Pokemon Card 151",
            is_target_japanese=True,
        )
        assert res_mb.status == "matched"
        assert res_mb.is_graded is True
        assert res_mb.grade == Decimal("10.0")

        # Standard card target should reject Master Ball title to prevent comp pollution
        res_std = parse_ebay_title(
            mb_title,
            target_card_name="Ivysaur - 002/165",
            target_card_number="002",
            target_set_name="SV2a: Pokemon Card 151",
            is_target_japanese=True,
        )
        assert res_std.status == "rejected"
        assert res_std.rejection_reason == RejectionReason.CARD_NAME_MISMATCH.value

    def test_japanese_sealed_product_matching(self) -> None:
        jp_box_title = "Pokemon Card 151 Japanese Booster Box SV2a Factory Sealed"
        res_box = parse_ebay_title(
            jp_box_title,
            target_card_name="151 Booster Box",
            target_card_number="",
            target_set_name="Pokemon Card 151",
            is_target_sealed=True,
            is_target_japanese=True,
        )
        assert res_box.status == "matched"
        assert res_box.condition == "Sealed"

        korean_box_title = "Pokemon Card 151 Korean Booster Box Factory Sealed"
        res_kor = parse_ebay_title(
            korean_box_title,
            target_card_name="151 Booster Box",
            target_card_number="",
            target_set_name="Pokemon Card 151",
            is_target_sealed=True,
            is_target_japanese=True,
        )
        assert res_kor.status == "rejected"
        assert res_kor.rejection_reason == RejectionReason.FOREIGN_LANGUAGE.value

