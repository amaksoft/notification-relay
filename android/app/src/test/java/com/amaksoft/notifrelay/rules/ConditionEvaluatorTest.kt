package com.amaksoft.notifrelay.rules

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.File

/**
 * Runs the exact same cross-language fixtures the Python condition_matcher
 * test suite uses (functions/tests/condition_fixtures.json), so the two
 * implementations can't silently drift apart — see docs/RULE_SCHEMA.md.
 */
class ConditionEvaluatorTest {

    private fun loadFixtures(): JSONArray {
        // Gradle unit tests run with cwd = the module dir (android/app);
        // functions/ is a sibling of android/ two levels up.
        val file = File("../../functions/tests/condition_fixtures.json")
        check(file.exists()) { "Fixtures file not found at ${file.absolutePath}" }
        return JSONArray(file.readText())
    }

    @Test
    fun `all shared fixtures match Python semantics`() {
        val fixtures = loadFixtures()
        for (i in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(i)
            val name = fixture.getString("name")
            val condition = fixture.getJSONObject("condition")
            val notification = fixture.getJSONObject("notification")
            val expected = fixture.getBoolean("expected")

            val actual = ConditionEvaluator.evaluate(condition, notification)
            assertEquals("fixture: $name", expected, actual)
        }
    }

    @Test
    fun `unknown condition type throws`() {
        assertThrows(IllegalArgumentException::class.java) {
            ConditionEvaluator.evaluate(JSONObject().put("type", "NOT_A_REAL_TYPE"), JSONObject())
        }
    }

    @Test
    fun `throttleAllows zero throttle always allows`() {
        assertEquals(true, ConditionEvaluator.throttleAllows(1000L, 0, 1000L))
    }

    @Test
    fun `throttleAllows never fired allows`() {
        assertEquals(true, ConditionEvaluator.throttleAllows(null, 30, 1000L))
    }

    @Test
    fun `throttleAllows within cooldown blocks`() {
        // lastFired at t=0, throttle=30s, now=10s later — still cooling down.
        assertEquals(false, ConditionEvaluator.throttleAllows(0L, 30, 10_000L))
    }

    @Test
    fun `throttleAllows after cooldown allows`() {
        // lastFired at t=0, throttle=30s, now=31s later — cooldown elapsed.
        assertEquals(true, ConditionEvaluator.throttleAllows(0L, 30, 31_000L))
    }

    @Test
    fun `throttleAllows exactly at boundary allows`() {
        assertEquals(true, ConditionEvaluator.throttleAllows(0L, 30, 30_000L))
    }

    @Test
    fun `ruleMatches respects enabled flag`() {
        val alwaysTrueCondition = JSONObject().put("type", "ALWAYS")
        val disabledRule = JSONObject().put("enabled", false).put("condition", alwaysTrueCondition)
        val enabledRule = JSONObject().put("enabled", true).put("condition", alwaysTrueCondition)
        assertEquals(false, ConditionEvaluator.ruleMatches(disabledRule, JSONObject()))
        assertEquals(true, ConditionEvaluator.ruleMatches(enabledRule, JSONObject()))
    }
}
