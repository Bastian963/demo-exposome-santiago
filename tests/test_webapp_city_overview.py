"""Tests for the CITY_OVERVIEW panel.

The panel is rendered when the user clicks a city marker on the LATAM
map. It shows the exposomes grouped by category (Entorno / Sociedad)
and lets the user click an exposome card to enter the COMMUNE state.
"""
from __future__ import annotations

import json
import re
import struct
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / "webapp" / "src" / "panels" / "city-overview.js"
PALETTE_JSON = REPO_ROOT / "webapp" / "public" / "palette.json"
INDEX_HTML = REPO_ROOT / "webapp" / "index.html"
MAIN_JS = REPO_ROOT / "webapp" / "src" / "main.js"
COMMUNE_JS = REPO_ROOT / "webapp" / "src" / "states" / "commune.js"
STYLE_CSS = REPO_ROOT / "webapp" / "src" / "style.css"
SOUND_JS = REPO_ROOT / "webapp" / "src" / "sound.js"
CONTROLLER_JS = REPO_ROOT / "webapp" / "src" / "components" / "exposomeAnimations" / "controller.js"
SOCIAL_RENDERER_JS = REPO_ROOT / "webapp" / "src" / "components" / "exposomeAnimations" / "renderers" / "social.js"
SPRITES_DIR = REPO_ROOT / "webapp" / "public" / "sprites" / "exposomes"


def _png_dimensions(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        data = f.read(24)
    return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]


class CityOverviewPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel_src = PANEL_JS.read_text()
        cls.palette = PALETTE_JSON.read_text()
        cls.index_html = INDEX_HTML.read_text()
        cls.main_src = MAIN_JS.read_text()
        cls.commune_src = COMMUNE_JS.read_text()
        cls.style_src = STYLE_CSS.read_text()

    def test_panel_file_exists(self) -> None:
        self.assertTrue(PANEL_JS.exists(), "city-overview.js must exist")

    def test_panel_exports_required_functions(self) -> None:
        for fn in (
            "export function initCityOverviewPanel",
            "export function showCityOverview",
            "export function hideCityOverview",
        ):
            self.assertIn(fn, self.panel_src, f"missing export: {fn}")

    def test_panel_renders_two_categories(self) -> None:
        self.assertIn("Naturales", self.panel_src)
        self.assertIn("Sociales", self.panel_src)

    def test_panel_handles_disabled_cards(self) -> None:
        self.assertIn("class=\"exposome-card", self.panel_src)
        self.assertIn("disabled", self.panel_src)
        self.assertIn("badge-coming-soon", self.panel_src)
        self.assertIn("badge-ready", self.panel_src)

    def test_panel_calls_back_callback(self) -> None:
        self.assertIn("cityPanelBack", self.panel_src)
        self.assertIn("_onBack", self.panel_src)

    def test_panel_calls_select_callback(self) -> None:
        self.assertIn("_onSelectExposome", self.panel_src)
        self.assertIn("card.dataset.id", self.panel_src)

    def test_panel_uses_escHtml(self) -> None:
        self.assertIn("function escHtml", self.panel_src)

    def test_panel_keyboard_support(self) -> None:
        self.assertIn("tabindex", self.panel_src)
        self.assertIn("Enter", self.panel_src)

    def test_show_hide_toggles_visible_class(self) -> None:
        self.assertIn('classList.add("visible")', self.panel_src)
        self.assertIn('classList.remove("visible")', self.panel_src)

    def test_layer_availability_prefers_manifest_columns(self) -> None:
        self.assertIn("getStudyManifest", self.panel_src)
        self.assertIn("columns", self.panel_src)

    def test_layer_availability_prefers_explicit_manifest_reason(self) -> None:
        self.assertIn("spatial_indicators", self.panel_src)
        self.assertIn("country_not_supported", self.panel_src)
        self.assertIn("not_enabled_by_study", self.panel_src)
        self.assertIn("supported_countries", self.panel_src)


class CityOverviewIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main_src = MAIN_JS.read_text()
        cls.index_html = INDEX_HTML.read_text()
        cls.commune_src = COMMUNE_JS.read_text()
        cls.style_src = STYLE_CSS.read_text()
        cls.palette = PALETTE_JSON.read_text()

    def test_index_html_has_city_overview_panel(self) -> None:
        self.assertIn('id="cityOverviewPanel"', self.index_html)
        self.assertIn("city-overview-panel", self.index_html)

    def test_main_js_has_city_state(self) -> None:
        self.assertIn('CITY: "city"', self.main_src)
        handle_idx = self.main_src.index("async function handleCityClick")
        handle_end = self.main_src.index("\n}", handle_idx) + 2
        handle_block = self.main_src[handle_idx:handle_end]
        self.assertIn("transitionToCity(city, generation)", handle_block)
        self.assertNotIn("transitionToCommune()", handle_block)

    def test_main_js_has_transitionToCity(self) -> None:
        self.assertIn("async function transitionToCity", self.main_src)

    def test_main_js_transitionToCommune_accepts_exposomeId(self) -> None:
        match = re.search(
            r"async function transitionToCommune\(([^)]*)\)",
            self.main_src,
        )
        self.assertIsNotNone(match, "transitionToCommune not found")
        params = match.group(1)
        self.assertIn("exposomeId", params)

    def test_main_js_back_button_handles_city_state(self) -> None:
        self.assertIn("_state === STATE.COMMUNE || _state === STATE.CITY", self.main_src)

    def test_commune_js_accepts_exposomeId(self) -> None:
        match = re.search(
            r"export async function initCommuneState\(([^)]*)\)",
            self.commune_src,
        )
        self.assertIsNotNone(match)
        params = match.group(1)
        self.assertIn("exposomeId", params)
        self.assertIn('exposomeId = "pm25"', self.commune_src)

    def test_commune_js_uses_exposomeId_for_choropleth(self) -> None:
        self.assertIn("addChoropleth(exposomeId)", self.commune_src)
        self.assertNotIn('addChoropleth("pm25")', self.commune_src)


class PaletteMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.palette = PALETTE_JSON.read_text()

    def test_palette_has_category_per_exposome(self) -> None:
        import json
        data = json.loads(self.palette)
        exposomes = data.get("exposomes", {})
        for ex_id, e in exposomes.items():
            self.assertIn("category", e, f"exposome {ex_id} missing category")
            self.assertIn(e["category"], ("entorno", "sociedad", "resultados"),
                          f"exposome {ex_id} has invalid category")

    def test_palette_has_icon_animated_per_exposome(self) -> None:
        import json
        data = json.loads(self.palette)
        exposomes = data.get("exposomes", {})
        for ex_id, e in exposomes.items():
            self.assertTrue(
                e.get("icon_animated") or e.get("icon_key"),
                f"exposome {ex_id} needs a sprite or code-native icon",
            )
            if e.get("icon_animated"):
                self.assertIn("icon_frames", e, f"exposome {ex_id} missing icon_frames")
            self.assertIn("status", e, f"exposome {ex_id} missing status")
            self.assertIn(e["status"], ("ready", "coming_soon", "group"),
                          f"exposome {ex_id} has invalid status")

    def test_pm25_is_ready(self) -> None:
        import json
        data = json.loads(self.palette)
        self.assertEqual(data["exposomes"]["pm25"]["status"], "ready")
        self.assertEqual(data["exposomes"]["pm25"]["category"], "entorno")

    def test_no2_is_ready(self) -> None:
        import json
        data = json.loads(self.palette)
        self.assertEqual(data["exposomes"]["no2"]["status"], "ready")
        self.assertEqual(data["exposomes"]["no2"]["category"], "entorno")

    def test_alan_is_ready(self) -> None:
        import json
        data = json.loads(self.palette)
        self.assertEqual(data["exposomes"]["alan"]["status"], "ready")
        self.assertTrue(data["exposomes"]["alan"]["has_fine_layer"])

    def test_nse_is_ready_contextual_social_layer(self) -> None:
        import json
        data = json.loads(self.palette)
        nse = data["exposomes"]["nse"]
        self.assertEqual(nse["status"], "ready")
        self.assertEqual(nse["category"], "sociedad")
        self.assertEqual(nse["column"], "nse_index")
        self.assertFalse(nse["has_fine_layer"])
        self.assertEqual(nse["resolution"], "comuna")
        self.assertEqual(nse["color"], "sequential_inv")
        self.assertEqual(nse["chamber"]["mode"], "social")
        self.assertEqual(nse["chamber"]["variant"], "socio_context")

    def test_social_infrastructure_is_ready_social_layer(self) -> None:
        import json
        data = json.loads(self.palette)
        social = data["exposomes"]["social_infrastructure"]
        self.assertEqual(social["status"], "ready")
        self.assertEqual(social["category"], "sociedad")
        self.assertEqual(social["column"], "social_index")
        self.assertFalse(social["has_fine_layer"])
        self.assertEqual(social["resolution"], "comuna")
        self.assertEqual(social["color"], "sequential_inv")
        self.assertEqual(social["chamber"]["mode"], "social")
        self.assertEqual(social["chamber"]["variant"], "social_assets")

    def test_noise_is_ready_environmental_layer_with_coverage_note(self) -> None:
        data = json.loads(self.palette)
        noise = data["exposomes"]["noise"]
        self.assertEqual(noise["status"], "ready")
        self.assertEqual(noise["category"], "entorno")
        self.assertEqual(noise["column"], "noise_combined_pct")
        self.assertFalse(noise["has_fine_layer"])
        self.assertEqual(noise["resolution"], "comuna / GSU model")
        self.assertEqual(noise["color"], "sequential")
        self.assertEqual(noise["coverage_column"], "noise_in_gsu_map")
        self.assertRegex(noise["coverage_note"], r"sin estimaci[oó]n")
        self.assertEqual(noise["chamber"]["mode"], "noise")
        self.assertEqual(noise["chamber"]["variant"], "traffic_noise")
        self.assertEqual(noise["sound"]["ambient"], "traffic_noise_loop")
        self.assertEqual(noise["sound"]["mode"], "direct")
        self.assertGreater(noise["sound"]["max_volume"], noise["sound"]["min_volume"])

    def test_rain_sublayers_have_reactive_sound(self) -> None:
        data = json.loads(self.palette)
        expected_modes = {
            "rain_index": "direct",
            "rain_annual": "direct",
            "rain_dry_spell": "inverse",
            "rain_heavy": "direct",
        }
        for ex_id, mode in expected_modes.items():
            sound = data["exposomes"][ex_id]["sound"]
            self.assertEqual(sound["ambient"], "rain_loop", f"{ex_id} must use rain loop")
            self.assertEqual(sound["mode"], mode, f"{ex_id} has wrong sound mode")
            self.assertGreaterEqual(sound["min_volume"], 0)
            self.assertGreater(sound["max_volume"], sound["min_volume"])

    def test_heat_is_group_with_ready_sublayers(self) -> None:
        import json
        data = json.loads(self.palette)
        heat = data["exposomes"]["heat"]
        self.assertEqual(heat["status"], "group")
        for ex_id in heat["children"]:
            self.assertEqual(
                data["exposomes"][ex_id]["status"],
                "ready",
                f"heat sublayer {ex_id} should be ready",
            )

    def test_heat_sublayers_have_distinct_monitor_variants(self) -> None:
        import json
        data = json.loads(self.palette)
        expected = {
            "heat_index": ("thermal_burden", -1.8, 1.7),
            "heat_summer_tmax": ("thermal_magnitude", 24, 32),
            "heat_hot_days": ("hot_day_register", 0, 105),
            "heat_tropical_nights": ("night_retention", 0, 20),
        }
        seen_copy = set()
        for ex_id, (variant, vmin, vmax) in expected.items():
            chamber = data["exposomes"][ex_id]["chamber"]
            self.assertEqual(chamber["variant"], variant)
            self.assertEqual(chamber["visual_min_value"], vmin)
            self.assertEqual(chamber["visual_max_value"], vmax)
            copy_key = (chamber["count_label"], chamber["scale_note"])
            self.assertNotIn(copy_key, seen_copy, f"{ex_id} duplicates monitor copy")
            seen_copy.add(copy_key)

    def test_remaining_exposomes_are_coming_soon(self) -> None:
        # "green" graduated to ready (Dynamic World + Meta canopy multi-source
        # layer); "ebi" is still pending.
        import json
        data = json.loads(self.palette)
        for ex_id in ("ebi",):
            self.assertEqual(
                data["exposomes"][ex_id]["status"],
                "coming_soon",
                f"exposome {ex_id} should be coming_soon",
            )

    def test_amba_parity_layers_are_ready_and_born_on_study_domain(self) -> None:
        """wildfire/healthcare/precipitation_spi/walkability/greenspace_access/
        wind ship with data in both Santiago and AMBA, so none of them should
        carry a hand-tuned visual_min_value/visual_max_value: the hybrid
        scaling engine (choropleth.js -> scaling.js resolveStudyBounds) is
        the only source of their chamber domain."""
        import json
        data = json.loads(self.palette)
        expected_columns = {
            "wildfire": "fire_exposure_index",
            "healthcare": "mean_nearest_health_m",
            "precipitation_spi": "drought_months_pct",
            "walkability": "walk_index",
            "greenspace_access": "dist_to_nearest_park_m",
            "wind": "wind_speed_mean",
        }
        for ex_id, column in expected_columns.items():
            expo = data["exposomes"][ex_id]
            self.assertEqual(expo["status"], "ready", f"{ex_id} should be ready")
            self.assertEqual(expo["column"], column, f"{ex_id} has unexpected column")
            self.assertIn(expo["category"], ("entorno", "sociedad"))
            chamber = expo["chamber"]
            self.assertNotIn(
                "visual_min_value", chamber,
                f"{ex_id} should rely on the study-domain engine, not a hand-tuned domain",
            )
            self.assertNotIn("visual_max_value", chamber)

    def test_new_exposome_labels_are_press_start_safe(self) -> None:
        """label and chamber.scene_label render in Press Start 2P (legend
        title, exposome-switcher chip), which has no accented uppercase
        glyphs -- see webapp/src/style.css .legend-title / feedback memory
        on webapp copy voice. Only VT323-rendered prose (description,
        help, caption) may use accents."""
        import json
        import re
        data = json.loads(self.palette)
        accented = re.compile(r"[áéíóúñÁÉÍÓÚÑ]")
        for ex_id in (
            "wildfire", "healthcare", "precipitation_spi",
            "walkability", "greenspace_access", "wind",
        ):
            expo = data["exposomes"][ex_id]
            self.assertNotRegex(expo["label"], accented, f"{ex_id} label breaks Press Start 2P")
            scene_label = expo["chamber"].get("scene_label", "")
            self.assertNotRegex(scene_label, accented, f"{ex_id} scene_label breaks Press Start 2P")


class SpriteAssetsTest(unittest.TestCase):
    TARGETED_ICON_IDS = (
        "wildfire",
        "precipitation_spi",
        "wind",
        "green",
        "canopy",
        "greenspace_access",
        "healthcare",
        "walkability",
        "poverty",
    )

    EXPECTED_IDS = (
        "pm25",
        "no2",
        "alan",
        "heat",
        "green",
        "ebi",
        "nse",
        "social_infrastructure",
        "noise",
        *TARGETED_ICON_IDS,
    )

    def test_sprites_dir_exists(self) -> None:
        self.assertTrue(SPRITES_DIR.exists(), f"sprites dir missing: {SPRITES_DIR}")

    def test_pm25_sprite_exists(self) -> None:
        self.assertTrue((SPRITES_DIR / "pm25.png").exists(), "pm25.png missing")

    def test_all_exposome_sprites_exist(self) -> None:
        for ex_id in self.EXPECTED_IDS:
            path = SPRITES_DIR / f"{ex_id}.png"
            self.assertTrue(path.exists(), f"missing sprite: {path}")

    def test_new_social_and_noise_icon_classes_exist(self) -> None:
        self.assertIn(".icon-social_infrastructure", STYLE_CSS.read_text())
        self.assertIn(".icon-noise", STYLE_CSS.read_text())

    def test_ready_spritesheet_dimensions(self) -> None:
        for ex_id in (
            "pm25", "no2", "alan", "nse", "social_infrastructure", "noise",
            *self.TARGETED_ICON_IDS,
        ):
            path = SPRITES_DIR / f"{ex_id}.png"
            if not path.exists():
                self.skipTest(f"{ex_id}.png not found")
            width, height = _png_dimensions(path)
            self.assertEqual(width, 128, f"{ex_id} width should be 128, got {width}")
            self.assertEqual(height, 32, f"{ex_id} height should be 32, got {height}")

    def test_pollution_and_alan_sprites_are_distinct(self) -> None:
        payloads = {
            ex_id: (SPRITES_DIR / f"{ex_id}.png").read_bytes()
            for ex_id in ("pm25", "no2", "alan")
        }
        self.assertNotEqual(payloads["pm25"], payloads["no2"])
        self.assertNotEqual(payloads["pm25"], payloads["alan"])
        self.assertNotEqual(payloads["no2"], payloads["alan"])

    def test_no2_css_uses_own_sprite(self) -> None:
        style = STYLE_CSS.read_text()
        self.assertIn('.icon-no2   { background-image: url("/sprites/exposomes/no2.png"); }', style)
        self.assertNotRegex(
            style,
            r"\.icon-no2\s*\{[^}]*pm25\.png",
            "NO2 must not reuse the PM2.5 sprite",
        )

    def test_targeted_icons_use_own_palette_path_and_css_rule(self) -> None:
        palette = json.loads(PALETTE_JSON.read_text())
        style = STYLE_CSS.read_text()
        for ex_id in self.TARGETED_ICON_IDS:
            self.assertEqual(
                palette["exposomes"][ex_id]["icon_animated"],
                f"/sprites/exposomes/{ex_id}.png",
            )
            self.assertIn(
                f'.icon-{ex_id} {{ background-image: url("/sprites/exposomes/{ex_id}.png"); }}',
                style,
            )

    def test_targeted_sprites_are_distinct(self) -> None:
        payloads = {
            ex_id: (SPRITES_DIR / f"{ex_id}.png").read_bytes()
            for ex_id in self.TARGETED_ICON_IDS
        }
        self.assertEqual(len(set(payloads.values())), len(payloads))

    def test_every_top_level_card_resolves_to_a_css_icon(self) -> None:
        palette = json.loads(PALETTE_JSON.read_text())
        style = STYLE_CSS.read_text()
        for ex_id, exposome in palette["exposomes"].items():
            if exposome.get("parent"):
                continue
            icon_key = exposome.get("icon_key") or ex_id
            self.assertRegex(
                style,
                rf"\.icon-{re.escape(icon_key)}(?:\s|,|\{{)",
                f"top-level card {ex_id} has no CSS icon rule for {icon_key}",
            )

    def test_reduced_motion_keeps_the_first_static_sprite_frame(self) -> None:
        style = STYLE_CSS.read_text()
        self.assertIn("@media (prefers-reduced-motion: reduce)", style)
        self.assertIn(".exposome-card-icon {\n    animation: none;\n    background-position: 0% 0;", style)

    def test_sprites_readme_exists(self) -> None:
        readme = SPRITES_DIR / "README.md"
        self.assertTrue(readme.exists(), "sprites/exposomes/README.md missing")
        content = readme.read_text()
        for keyword in ("128x32", "CSS", "frames", "4 frames"):
            self.assertIn(keyword, content, f"README missing info about: {keyword}")


class SoundSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sound_src = SOUND_JS.read_text()
        cls.main_src = MAIN_JS.read_text()
        cls.controller_src = CONTROLLER_JS.read_text()

    def test_reactive_sound_exports_exist(self) -> None:
        for expected in (
            "export function setActiveAmbient",
            "export function setReactiveIntensity",
            "export function clearReactiveIntensity",
            "export function stopAmbient",
        ):
            self.assertIn(expected, self.sound_src)
        self.assertIn("rain_loop.wav", self.sound_src)
        self.assertIn("traffic_noise_loop.wav", self.sound_src)

    def test_commune_entry_does_not_start_global_smog_loop(self) -> None:
        self.assertNotIn('play("smog_loop")', self.main_src)

    def test_monitor_controller_drives_reactive_sound(self) -> None:
        self.assertIn("setActiveAmbient(_expo)", self.controller_src)
        self.assertIn("setReactiveIntensity(_targetState.intensity)", self.controller_src)
        self.assertIn("clearReactiveIntensity()", self.controller_src)


class SocialInfrastructureMonitorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.renderer_src = SOCIAL_RENDERER_JS.read_text()

    def test_social_assets_variant_has_city_monitor(self) -> None:
        self.assertIn('theme?.variant === "social_assets"', self.renderer_src)
        self.assertIn("drawSocialInfrastructureMonitor", self.renderer_src)
        self.assertIn("drawDistrictBase", self.renderer_src)
        self.assertIn("drawAccessNetwork", self.renderer_src)
        self.assertIn("drawParkNode", self.renderer_src)
        self.assertIn("drawHealthNode", self.renderer_src)

    def test_nse_monitor_path_is_preserved(self) -> None:
        self.assertIn("drawSocioeconomicMonitor", self.renderer_src)
        self.assertIn("drawStrataBars", self.renderer_src)


if __name__ == "__main__":
    unittest.main()
