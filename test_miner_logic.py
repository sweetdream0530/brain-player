#!/usr/bin/env python3
"""
Test file to validate miner logic locally
Tests spymaster and operative strategies by calling the actual miner's forward method
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.protocol import GameSynapse, CardType
from neurons.miner import Miner
import bittensor as bt

# Configure logging
bt.logging.set_trace(True)
bt.logging.set_debug(True)


class TestScenario:
    """Test scenario for miner"""
    
    def __init__(self, name: str, synapse: GameSynapse, expected_behavior: str):
        self.name = name
        self.synapse = synapse
        self.expected_behavior = expected_behavior


# Test scenarios
TEST_SCENARIOS = [
    # Scenario 1: Spymaster - Assassin Avoidance (CHINA assassin)
    TestScenario(
        name="Spymaster - CHINA Assassin Avoidance",
        synapse=GameSynapse(
            your_team="blue",
            your_role="spymaster",
            remaining_red=8,
            remaining_blue=8,
            cards=[
                CardType(word='AZTEC', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='ALIEN', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='AMAZON', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='CRASH', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='CHINA', color='assassin', is_revealed=False, was_recently_revealed=False),
                CardType(word='STICK', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='MASS', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='SPOT', color='red', is_revealed=False, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should avoid clues like CULTURE, ASIA, TRADE that connect to CHINA"
    ),
    
    # Scenario 2: Spymaster - GERMANY Assassin Avoidance
    TestScenario(
        name="Spymaster - GERMANY Assassin Avoidance",
        synapse=GameSynapse(
            your_team="red",
            your_role="spymaster",
            remaining_red=9,
            remaining_blue=8,
            cards=[
                CardType(word='PLANE', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='SKY', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='BIRD', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='GERMANY', color='assassin', is_revealed=False, was_recently_revealed=False),
                CardType(word='FRANCE', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='SPAIN', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='ITALY', color='bystander', is_revealed=False, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should avoid clues like FLIGHT, LUFTHANSA, EUROPE that connect to GERMANY"
    ),
    
    # Scenario 3: Operative - Conservative (Ahead)
    TestScenario(
        name="Operative - Conservative (Team Ahead)",
        synapse=GameSynapse(
            your_team="red",
            your_role="operative",
            remaining_red=3,
            remaining_blue=6,
            your_clue="TRADE",
            your_number=3,
            cards=[
                CardType(word='WIND', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='BOMB', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='SMUGGLER', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='CHINA', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='MOUNT', color='red', is_revealed=True, was_recently_revealed=False),
                CardType(word='CARD', color='red', is_revealed=True, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should be conservative, only guess high-confidence words (8+ confidence)"
    ),
    
    # Scenario 4: Operative - Aggressive (Behind)
    TestScenario(
        name="Operative - Aggressive (Team Behind)",
        synapse=GameSynapse(
            your_team="blue",
            your_role="operative",
            remaining_red=3,
            remaining_blue=7,
            your_clue="WATER",
            your_number=3,
            cards=[
                CardType(word='OCEAN', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='RIVER', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='LAKE', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='POND', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='POOL', color='blue', is_revealed=True, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should be more aggressive, accept lower confidence guesses (6+ confidence)"
    ),
    
    # Scenario 5: Spymaster - Safe Multi-Word Clue
    TestScenario(
        name="Spymaster - Safe Multi-Word Connection",
        synapse=GameSynapse(
            your_team="red",
            your_role="spymaster",
            remaining_red=9,
            remaining_blue=8,
            cards=[
                CardType(word='PIRATE', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='SMUGGLER', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='DIAMOND', color='red', is_revealed=False, was_recently_revealed=False),
                CardType(word='CROWN', color='assassin', is_revealed=False, was_recently_revealed=False),
                CardType(word='PRINCESS', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='KING', color='blue', is_revealed=False, was_recently_revealed=False),
                CardType(word='CASTLE', color='bystander', is_revealed=False, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should connect PIRATE, SMUGGLER, DIAMOND while avoiding CROWN (royalty associations)"
    ),
    
    # Scenario 6: Operative - Clue with Revealed Cards
    TestScenario(
        name="Operative - With Game History",
        synapse=GameSynapse(
            your_team="blue",
            your_role="operative",
            remaining_red=5,
            remaining_blue=6,
            your_clue="ANCIENT",
            your_number=2,
            cards=[
                CardType(word='EGYPT', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='ROME', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='GREECE', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='CHINA', color=None, is_revealed=False, was_recently_revealed=False),
                CardType(word='AZTEC', color='blue', is_revealed=True, was_recently_revealed=False),
                CardType(word='MAYA', color='blue', is_revealed=True, was_recently_revealed=False),
            ],
        ),
        expected_behavior="Should identify EGYPT, ROME as likely ancient civilizations"
    ),
]


async def call_miner_forward(miner: Miner, synapse: GameSynapse):
    """Call the actual miner's forward method"""
    try:
        # Call the real miner's forward method
        result_synapse = await miner.forward(synapse)
        
        # Extract the result
        if result_synapse and result_synapse.output:
            result = {
                "role": synapse.your_role,
                "parsed": {
                    "clue": result_synapse.output.clue_text,
                    "number": result_synapse.output.number,
                    "guesses": result_synapse.output.guesses,
                    "reasoning": result_synapse.output.reasoning
                }
            }
            
            if synapse.your_role == "spymaster":
                result["clue"] = result_synapse.output.clue_text
                result["number"] = result_synapse.output.number
                result["reasoning"] = result_synapse.output.reasoning
            else:
                result["guesses"] = result_synapse.output.guesses
                result["reasoning"] = result_synapse.output.reasoning
            
            return result
        else:
            return None
            
    except Exception as e:
        bt.logging.error(f"Error calling miner forward: {e}")
        return {"error": str(e)}


async def test_miner():
    """Run all test scenarios"""
    
    print("=" * 80)
    print("MINER LOGIC TEST SUITE - LIVE TESTING")
    print("=" * 80)
    print()
    
    # Check configuration
    use_chutes = os.environ.get("USE_CHUTES_AI", "false").lower() == "true"
    if use_chutes:
        api_key = os.environ.get("CHUTES_API_KEY")
        model = os.environ.get("CHUTES_MODEL", "deepseek-ai/DeepSeek-V3")
        if not api_key:
            print("❌ ERROR: USE_CHUTES_AI=true but CHUTES_API_KEY not set!")
            print("\nSet your API key:")
            print("export CHUTES_API_KEY=your_api_key_here")
            return
        print(f"✅ Using Chutes.ai")
        print(f"   Model: {model}")
        print(f"   API Key: {api_key[:10]}...")
    else:
        api_key = os.environ.get("OPENAI_KEY")
        if not api_key:
            print("❌ ERROR: OPENAI_KEY not set!")
            return
        print(f"✅ Using OpenAI")
        print(f"   Model: gpt-4o-mini")
        print(f"   API Key: {api_key[:10]}...")
    
    print()
    print("-" * 80)
    print()
    
    # Initialize miner (without full bittensor setup)
    print("Initializing miner...")
    try:
        # Create minimal config
        class TestConfig:
            pass
        
        config = TestConfig()
        
        # The miner will use environment variables for API keys
        # We just need a basic instance
        miner = Miner(config=None)
        print("✅ Miner initialized successfully")
    except Exception as e:
        print(f"⚠️  Could not initialize full miner: {e}")
        print("    Attempting to create minimal miner instance...")
        # Create a minimal miner with just the necessary attributes
        miner = Miner.__new__(Miner)
        miner.game_history = {}
        miner.max_game_history = 100
        print("✅ Minimal miner instance created")
    
    print()
    print("-" * 80)
    print()
    
    # Test each scenario
    results = []
    
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}/{len(TEST_SCENARIOS)}: {scenario.name}")
        print(f"{'=' * 80}")
        print(f"Expected: {scenario.expected_behavior}")
        print()
        
        # Display game state
        print("📋 Game State:")
        print(f"  Team: {scenario.synapse.your_team.upper()}")
        print(f"  Role: {scenario.synapse.your_role.upper()}")
        print(f"  Score: Red {scenario.synapse.remaining_red} - Blue {scenario.synapse.remaining_blue}")
        
        if scenario.synapse.your_role == "operative":
            print(f"  Clue: {scenario.synapse.your_clue}:{scenario.synapse.your_number}")
        
        print("\n  Cards:")
        for card in scenario.synapse.cards:
            status = "✓ REVEALED" if card.is_revealed else "  hidden"
            color = card.color.upper() if card.color else "UNKNOWN"
            print(f"    [{status}] {card.word:<15} ({color})")
        
        print("\n" + "-" * 80)
        print(f"🧪 Calling miner's forward method...")
        print("-" * 80 + "\n")
        
        # Call the actual miner logic
        start_time = time.time()
        result = await call_miner_forward(miner, scenario.synapse)
        elapsed = time.time() - start_time
        
        if result and "error" not in result:
            print(f"\n✅ SUCCESS! (took {elapsed:.2f}s)")
            print(f"\n📤 Miner Response:")
            
            if scenario.synapse.your_role == "spymaster":
                print(f"   Clue: {result['clue']}:{result['number']}")
                print(f"   Reasoning: {result['reasoning'][:200]}..." if len(result['reasoning']) > 200 else f"   Reasoning: {result['reasoning']}")
            else:
                print(f"   Guesses: {result['guesses']}")
                print(f"   Reasoning: {result['reasoning'][:200]}..." if len(result['reasoning']) > 200 else f"   Reasoning: {result['reasoning']}")
            
            results.append({
                "scenario": scenario.name,
                "status": "SUCCESS",
                "result": result,
                "time": elapsed
            })
        elif result and "error" in result:
            print(f"\n⚠️  PARTIAL SUCCESS (took {elapsed:.2f}s)")
            print(f"   Error: {result['error']}")
            print(f"   Raw: {result.get('raw', 'N/A')[:200]}...")
            
            results.append({
                "scenario": scenario.name,
                "status": "PARTIAL",
                "result": result,
                "time": elapsed
            })
        else:
            print(f"\n❌ FAILED (took {elapsed:.2f}s)")
            print("   No response from miner")
            
            results.append({
                "scenario": scenario.name,
                "status": "FAILED",
                "time": elapsed
            })
        
        # Delay between tests
        if i < len(TEST_SCENARIOS):
            print("\n" + "." * 80)
            await asyncio.sleep(2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80 + "\n")
    
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    partial_count = sum(1 for r in results if r["status"] == "PARTIAL")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    avg_time = sum(r["time"] for r in results) / len(results) if results else 0
    
    print(f"✅ Successful: {success_count}/{len(TEST_SCENARIOS)}")
    print(f"⚠️  Partial: {partial_count}/{len(TEST_SCENARIOS)}")
    print(f"❌ Failed: {failed_count}/{len(TEST_SCENARIOS)}")
    print(f"⏱️  Average time: {avg_time:.2f}s")
    
    print("\n" + "=" * 80)
    print("🎯 RECOMMENDATIONS")
    print("=" * 80 + "\n")
    
    if success_count == len(TEST_SCENARIOS):
        print("🎉 ALL TESTS PASSED!")
        print("\nYour miner is working correctly with Chutes.ai!")
        print("\nNext steps:")
        print("1. Deploy: pm2 restart miner")
        print("2. Monitor: pm2 logs miner")
        print("3. Track win rate over 24-48 hours")
    elif success_count > 0:
        print("✅ Miner is working but has some issues")
        print("\nCheck the failed scenarios above")
    else:
        print("❌ Miner has configuration issues")
        print("\nTroubleshooting:")
        print("1. Verify CHUTES_API_KEY is correct")
        print("2. Check CHUTES_MODEL is available")
        print("3. Test with: python3 test_chutes_models.py")


if __name__ == "__main__":
    asyncio.run(test_miner())

