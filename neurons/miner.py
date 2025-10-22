# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 plebgang

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import time
import typing
import json
import ast
import bittensor as bt
import os
import httpx
from dotenv import load_dotenv
import game
from game.utils.ruleSysPrompt import ruleSysPrompt
from game.utils.spySysPrompt import spySysPrompt
from game.utils.opSysPrompt import opSysPrompt

# Bittensor Miner Template:
from game.protocol import GameSynapse, GameSynapseOutput, Ping

from openai import OpenAI
from openai import (
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)

# import base miner class which takes care of most of the boilerplate
from game.base.miner import BaseMinerNeuron

load_dotenv()


class Miner(BaseMinerNeuron):
    """
    Your miner neuron class. You should use this class to define your miner's behavior. In particular, you should replace the forward function with your own logic. You may also want to override the blacklist and priority functions according to your needs.

    This class inherits from the BaseMinerNeuron class, which in turn inherits from BaseNeuron. The BaseNeuron class takes care of routine tasks such as setting up wallet, subtensor, metagraph, logging directory, parsing config, etc. You can override any of the methods in BaseNeuron if you need to customize the behavior.

    This class provides reasonable default behavior for a miner such as blacklisting unrecognized hotkeys, prioritizing requests based on stake, and forwarding requests to the forward function. If you need to define custom
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        if not self.check_openai_key():
            raise ValueError("Invalid OPENAI_KEY environment variable.")
        self.axon.attach(
            forward_fn=self.pong,
            blacklist_fn=self.blacklist_ping,
        )
        # Track game history for strategic awareness
        self.game_history = {}
        # Cleanup old games periodically (keep last 100)
        self.max_game_history = 100

    def check_openai_key(self):
        retries = 3
        timeout = 5
        client = OpenAI(timeout=timeout, api_key=os.environ.get("OPENAI_KEY"))
        last_err = None

        for attempt in range(retries + 1):
            try:
                _ = client.responses.create(
                    model="gpt-4o-mini",
                    input="api key test",
                    max_output_tokens=16,
                )
                return True
            except AuthenticationError as e:
                bt.logging.error(f"AUTH ERROR: {e}")
                return False
            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
            ) as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as e:  # safety net
                last_err = e
                break
        if last_err:
            bt.logging.error(f"FAILED: {last_err}")
            return False
        return True

    async def pong(self, synapse: Ping) -> Ping:
        """
        Responds to a Ping with a Pong response, indicating the miner's availability.

        Args:
            synapse (Ping): The incoming ping synapse from a validator.

        Returns:
            Ping: The response synapse with the is_available field set to True.
        """
        bt.logging.info("💌 Received Ping request")
        synapse.is_available = True
        return synapse

    def get_game_id(self, cards):
        """Generate unique game ID from board state"""
        return hash(tuple(sorted([c.word for c in cards])))
    
    def cleanup_old_games(self):
        """Remove old game history to prevent memory bloat"""
        if len(self.game_history) > self.max_game_history:
            # Remove oldest 20 games
            sorted_games = sorted(self.game_history.items(), key=lambda x: x[1].get('last_updated', 0))
            for game_id, _ in sorted_games[:20]:
                del self.game_history[game_id]
    
    def update_game_history(self, game_id, role, clue=None, guesses=None, is_our_turn=True):
        """Track game history for strategic awareness"""
        if game_id not in self.game_history:
            self.game_history[game_id] = {
                'our_clues': [],
                'our_guesses': [],
                'opponent_clues': [],
                'last_updated': time.time()
            }
        
        game = self.game_history[game_id]
        game['last_updated'] = time.time()
        
        if role == "spymaster" and clue and is_our_turn:
            game['our_clues'].append(clue)
        elif role == "operative" and guesses and is_our_turn:
            game['our_guesses'].extend(guesses)
        elif role == "spymaster" and clue and not is_our_turn:
            game['opponent_clues'].append(clue)
    
    def get_game_context(self, game_id):
        """Get historical context for current game"""
        if game_id not in self.game_history:
            return None
        return self.game_history[game_id]
    
    def identify_assassin(self, cards):
        """Identify the assassin card from the board"""
        for card in cards:
            if hasattr(card, 'color') and card.color == 'assassin':
                return card.word
        return None
    
    def analyze_revealed_cards(self, cards, your_team):
        """Analyze revealed cards for strategic insights"""
        revealed = {
            'our_team': [],
            'opponent': [],
            'neutral': [],
            'assassin_revealed': False
        }
        
        opponent_team = 'blue' if your_team == 'red' else 'red'
        
        for card in cards:
            if card.is_revealed:
                if card.color == your_team:
                    revealed['our_team'].append(card.word)
                elif card.color == opponent_team:
                    revealed['opponent'].append(card.word)
                elif card.color == 'neutral':
                    revealed['neutral'].append(card.word)
                elif card.color == 'assassin':
                    revealed['assassin_revealed'] = True
        
        return revealed
    
    def infer_opponent_targets(self, opponent_clues, revealed_opponent_words):
        """Infer what words opponent is targeting based on their clues"""
        if not opponent_clues:
            return []
        
        # Simple heuristic: words they've revealed are related to their clues
        # This helps us avoid those words
        return revealed_opponent_words
    
    def validate_clue(self, clue: str, board_words: list) -> bool:
        """
        Pre-validate a clue to ensure it doesn't contain board words or their substrings.
        Enhanced with word stem checking to catch similar word forms.
        This helps avoid invalid clue penalties.
        """
        if not clue:
            return False
        
        clue_lower = clue.lower().strip()
        
        # Check if clue is any board word or contains board word as substring
        for word in board_words:
            word_lower = word.lower().strip()
            
            # Check exact match
            if clue_lower == word_lower:
                bt.logging.warning(f"Clue '{clue}' matches board word '{word}'")
                return False
            
            # Check if board word is substring of clue (e.g., OCEAN in OCEANIC)
            if word_lower in clue_lower or clue_lower in word_lower:
                bt.logging.warning(f"Clue '{clue}' contains/is contained in board word '{word}'")
                return False
            
            # NEW: Check word stems for similar forms (e.g., WALK vs WALKING)
            # If both words are 4+ chars, check if first 4 chars match
            if len(word_lower) >= 4 and len(clue_lower) >= 4:
                if word_lower[:4] == clue_lower[:4]:
                    bt.logging.warning(f"Clue '{clue}' has similar stem to board word '{word}' (both start with '{word_lower[:4]}')")
                    return False
            
            # Check common plural/past tense forms
            # If board word ends in common suffixes, check clue for base form
            if word_lower.endswith('s') and len(word_lower) > 2:
                base = word_lower[:-1]  # Remove 's'
                if base == clue_lower or base in clue_lower or clue_lower in base:
                    bt.logging.warning(f"Clue '{clue}' may be singular form of board word '{word}'")
                    return False
            
            if word_lower.endswith('ed') and len(word_lower) > 3:
                base = word_lower[:-2]  # Remove 'ed'
                if base == clue_lower or base in clue_lower or clue_lower in base:
                    bt.logging.warning(f"Clue '{clue}' may be base form of past tense board word '{word}'")
                    return False
            
            if word_lower.endswith('ing') and len(word_lower) > 4:
                base = word_lower[:-3]  # Remove 'ing'
                if base == clue_lower or base in clue_lower or clue_lower in base:
                    bt.logging.warning(f"Clue '{clue}' may be base form of -ing board word '{word}'")
                    return False
        
        return True

    async def forward(
        self, synapse: game.protocol.GameSynapse
    ) -> game.protocol.GameSynapse:
        """
        Handles the incoming 'GameSynapse' by executing a series of operations based on the game state.
        This method should be customized to implement the specific logic required for the miner's function.

        Args:
            synapse (game.protocol.GameSynapse): The synapse object containing the game state data.

        Returns:
            game.protocol.GameSynapse: The synapse object with updated fields based on the miner's processing logic.

        The 'forward' function is a template and should be tailored to fit the miner's specific operational needs.
        This method illustrates a basic framework for processing game-related data.
        """

        bt.logging.info("💌 Received GameSynapse request")
        
        # Cleanup old games periodically
        self.cleanup_old_games()
        
        # Get game ID for history tracking
        game_id = self.get_game_id(synapse.cards)
        game_context = self.get_game_context(game_id)

        async def get_gpt5_response(messages):
            try:
                client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
                result = client.responses.create(
                    model="gpt-5",
                    input=messages,
                    reasoning={
                        "effort": "minimal"
                    },  # Optional: control reasoning effort
                )
                return result.output_text
            except Exception as e:
                bt.logging.error(f"Error fetching response from GPT-4: {e}")
                return None

        # Build board and clue strings outside the f-string to avoid backslash-in-expression errors.
        messages = []
        if synapse.your_role == "operative":
            board = [
                {
                    "word": card.word,
                    "isRevealed": card.is_revealed,
                    "color": card.color if card.is_revealed else None,
                }
                for card in synapse.cards
            ]
            clue_block = (
                f"Your Clue: {synapse.your_clue}\nNumber: {synapse.your_number}"
            )
            # Get unrevealed words for operative context
            unrevealed_words = [card.word for card in synapse.cards if not card.is_revealed]
        else:
            board = synapse.cards
            clue_block = ""
            # For spymaster, get all board words for validation
            unrevealed_words = [card.word for card in synapse.cards if not card.is_revealed]

        # Calculate game state for strategic decision making
        my_cards_left = synapse.remaining_red if synapse.your_team == "red" else synapse.remaining_blue
        opponent_cards_left = synapse.remaining_blue if synapse.your_team == "red" else synapse.remaining_red
        
        # Determine if we're ahead or behind
        if my_cards_left < opponent_cards_left:
            position = "ahead"
        elif my_cards_left > opponent_cards_left:
            position = "behind"
        else:
            position = "tied"
        
        # Analyze revealed cards for strategic insights
        revealed_analysis = self.analyze_revealed_cards(synapse.cards, synapse.your_team)
        
        # Identify assassin (only visible to spymaster)
        assassin_word = None
        if synapse.your_role == "spymaster":
            assassin_word = self.identify_assassin(synapse.cards)
        
        # Get opponent intelligence
        likely_opponent_words = []
        if game_context:
            likely_opponent_words = self.infer_opponent_targets(
                game_context.get('opponent_clues', []),
                revealed_analysis['opponent']
            )

        # Enhanced strategic instructions
        strategic_context = ""
        if synapse.your_role == "spymaster":
            # Build assassin warning
            assassin_warning = ""
            if assassin_word:
                # Identify team words that are dangerously close to assassin
                dangerous_team_words = []
                assassin_lower = assassin_word.lower()
                
                # Enhanced associations map (expanded from game analysis and common assassin words)
                assassin_related_terms = {
                    'crown': ['princess', 'prince', 'king', 'queen', 'royal', 'jewel', 'gem', 'treasure', 'throne', 'monarch', 'jewelry', 'palace', 'castle', 'noble', 'royalty', 'empire', 'crown', 'diadem', 'tiara'],
                    'germany': ['berlin', 'munich', 'beer', 'sausage', 'nazi', 'europe', 'flight', 'lufthansa', 'bmw', 'mercedes', 'audi', 'volkswagen', 'oktoberfest', 'lederhosen', 'rhine', 'alps', 'bundesliga', 'chancellor', 'autobahn'],
                    'china': ['beijing', 'asia', 'dragon', 'wall', 'culture', 'emperor', 'shanghai', 'silk', 'tea', 'panda', 'confucius', 'temple', 'buddha', 'mandarin', 'communist', 'tiananmen', 'yangtze', 'terracotta'],
                    'yard': ['garden', 'lawn', 'grass', 'backyard', 'school', 'front', 'fence', 'patio', 'deck', 'outdoor', 'landscape', 'trees', 'flowers'],
                    'pound': ['currency', 'british', 'england', 'uk', 'sterling', 'weight', 'money', 'london', 'queen', 'crown', 'britain', 'pence', 'shilling'],
                    'bank': ['money', 'finance', 'river', 'account', 'loan', 'vault', 'deposit', 'credit', 'debit', 'atm', 'teller', 'cash', 'investment', 'interest'],
                    'table': ['dining', 'chair', 'furniture', 'desk', 'kitchen', 'dinner', 'restaurant', 'meal', 'food', 'eat', 'plate', 'cup', 'spoon', 'fork', 'knife'],
                    'rock': ['stone', 'music', 'band', 'roll', 'mountain', 'cliff', 'boulder', 'pebble', 'granite', 'marble', 'mineral', 'geology', 'earth', 'ground'],
                    'star': ['celebrity', 'hollywood', 'famous', 'sky', 'space', 'astronomy', 'constellation', 'galaxy', 'planet', 'sun', 'moon', 'night', 'bright', 'shine'],
                    'strike': ['bowling', 'baseball', 'labor', 'protest', 'hit', 'attack', 'union', 'worker', 'job', 'employment', 'work', 'action', 'walkout'],
                    'tablet': ['medicine', 'pill', 'drug', 'pharmacy', 'prescription', 'doctor', 'health', 'medical', 'ipad', 'computer', 'screen', 'digital', 'electronic', 'apple', 'samsung'],
                    'bottle': ['drink', 'water', 'beer', 'wine', 'glass', 'container', 'liquid', 'beverage', 'alcohol', 'soda', 'juice', 'milk', 'cork', 'cap'],
                    'plane': ['aircraft', 'flight', 'airport', 'pilot', 'airline', 'travel', 'sky', 'wing', 'engine', 'aviation', 'jet', 'boeing', 'airbus', 'ticket'],
                    'train': ['railroad', 'station', 'track', 'locomotive', 'subway', 'metro', 'travel', 'transport', 'engine', 'car', 'passenger', 'freight', 'railway'],
                    'church': ['religion', 'god', 'jesus', 'christian', 'bible', 'prayer', 'faith', 'worship', 'priest', 'pastor', 'mass', 'service', 'holy', 'sacred'],
                    'night': ['dark', 'evening', 'sleep', 'bed', 'moon', 'stars', 'shadow', 'black', 'late', 'time', 'dream', 'rest', 'quiet', 'silence'],
                    'spot': ['dot', 'mark', 'stain', 'place', 'location', 'position', 'point', 'area', 'region', 'zone', 'territory', 'site', 'venue'],
                    'bomb': ['explosive', 'blast', 'boom', 'danger', 'threat', 'war', 'military', 'weapon', 'attack', 'terror', 'violence', 'destruction', 'fire'],
                    'cap': ['hat', 'head', 'top', 'lid', 'cover', 'crown', 'peak', 'baseball', 'sports', 'team', 'uniform', 'clothing', 'accessory'],
                    'staff': ['stick', 'rod', 'pole', 'cane', 'walking', 'support', 'employee', 'worker', 'personnel', 'team', 'crew', 'group', 'organization'],
                    'ham': ['meat', 'pork', 'food', 'sandwich', 'lunch', 'dinner', 'breakfast', 'eat', 'meal', 'protein', 'cooking', 'kitchen', 'delicious'],
                    'hotel': ['accommodation', 'room', 'stay', 'travel', 'vacation', 'trip', 'guest', 'reception', 'lobby', 'service', 'hospitality', 'booking', 'reservation'],
                    'button': ['press', 'click', 'control', 'switch', 'device', 'electronic', 'computer', 'keyboard', 'remote', 'interface', 'shirt', 'clothing', 'fastener'],
                    'centaur': ['mythology', 'mythical', 'creature', 'horse', 'human', 'fantasy', 'legend', 'ancient', 'greek', 'story', 'magical', 'fictional', 'imaginary'],
                    'stream': ['river', 'water', 'flow', 'current', 'brook', 'creek', 'flowing', 'liquid', 'fresh', 'nature', 'outdoor', 'landscape', 'peaceful'],
                    'dance': ['music', 'movement', 'rhythm', 'party', 'celebration', 'entertainment', 'performance', 'art', 'culture', 'social', 'fun', 'activity'],
                    'america': ['usa', 'united', 'states', 'country', 'nation', 'patriot', 'freedom', 'liberty', 'democracy', 'president', 'government', 'flag', 'star'],
                    'pool': ['water', 'swimming', 'swim', 'dive', 'sport', 'exercise', 'recreation', 'leisure', 'summer', 'hot', 'cool', 'refresh', 'fun'],
                    'mass': ['weight', 'heavy', 'size', 'bulk', 'volume', 'physics', 'science', 'measurement', 'church', 'service', 'religion', 'christian', 'catholic'],
                    'thief': ['steal', 'rob', 'crime', 'criminal', 'burglar', 'bandit', 'outlaw', 'bad', 'evil', 'illegal', 'justice', 'police', 'law'],
                    'rose': ['flower', 'plant', 'garden', 'beautiful', 'romantic', 'love', 'red', 'petals', 'thorn', 'nature', 'outdoor', 'gardening', 'bloom', 'actor', 'actress', 'rose byrne', 'hollywood', 'celebrity', 'famous', 'entertainment', 'film', 'movie', 'star', 'cast', 'theater', 'drama', 'performance'],
                    'screen': ['display', 'monitor', 'computer', 'television', 'tv', 'movie', 'film', 'entertainment', 'digital', 'electronic', 'image', 'picture', 'visual'],
                    'organ': ['music', 'instrument', 'keyboard', 'church', 'pipe', 'sound', 'melody', 'harmony', 'classical', 'concert', 'performance', 'musical', 'art'],
                    'brush': ['paint', 'art', 'artist', 'painting', 'color', 'canvas', 'creative', 'tool', 'hair', 'comb', 'grooming', 'beauty', 'makeup'],
                    'tube': ['pipe', 'cylinder', 'round', 'hollow', 'music', 'amplifier', 'sound', 'electronic', 'technology', 'transport', 'subway', 'metro', 'underground'],
                    'fighter': ['warrior', 'soldier', 'combat', 'battle', 'war', 'military', 'defense', 'attack', 'weapon', 'strength', 'courage', 'brave', 'hero'],
                    'spot': ['location', 'place', 'position', 'area', 'region', 'zone', 'site', 'venue', 'dot', 'mark', 'stain', 'point', 'target'],
                    'bomb': ['explosive', 'blast', 'boom', 'danger', 'threat', 'war', 'military', 'weapon', 'attack', 'terror', 'violence', 'destruction', 'fire'],
                    'cap': ['hat', 'head', 'top', 'lid', 'cover', 'crown', 'peak', 'baseball', 'sports', 'team', 'uniform', 'clothing', 'accessory'],
                    'staff': ['stick', 'rod', 'pole', 'cane', 'walking', 'support', 'employee', 'worker', 'personnel', 'team', 'crew', 'group', 'organization'],
                    'ham': ['meat', 'pork', 'food', 'sandwich', 'lunch', 'dinner', 'breakfast', 'eat', 'meal', 'protein', 'cooking', 'kitchen', 'delicious'],
                    'hotel': ['accommodation', 'room', 'stay', 'travel', 'vacation', 'trip', 'guest', 'reception', 'lobby', 'service', 'hospitality', 'booking', 'reservation'],
                    'button': ['press', 'click', 'control', 'switch', 'device', 'electronic', 'computer', 'keyboard', 'remote', 'interface', 'shirt', 'clothing', 'fastener'],
                    'centaur': ['mythology', 'mythical', 'creature', 'horse', 'human', 'fantasy', 'legend', 'ancient', 'greek', 'story', 'magical', 'fictional', 'imaginary'],
                    'stream': ['river', 'water', 'flow', 'current', 'brook', 'creek', 'flowing', 'liquid', 'fresh', 'nature', 'outdoor', 'landscape', 'peaceful'],
                    'dance': ['music', 'movement', 'rhythm', 'party', 'celebration', 'entertainment', 'performance', 'art', 'culture', 'social', 'fun', 'activity'],
                    'america': ['usa', 'united', 'states', 'country', 'nation', 'patriot', 'freedom', 'liberty', 'democracy', 'president', 'government', 'flag', 'star'],
                    'pool': ['water', 'swimming', 'swim', 'dive', 'sport', 'exercise', 'recreation', 'leisure', 'summer', 'hot', 'cool', 'refresh', 'fun'],
                    'mass': ['weight', 'heavy', 'size', 'bulk', 'volume', 'physics', 'science', 'measurement', 'church', 'service', 'religion', 'christian', 'catholic'],
                    'thief': ['steal', 'rob', 'crime', 'criminal', 'burglar', 'bandit', 'outlaw', 'bad', 'evil', 'illegal', 'justice', 'police', 'law'],
                    'rose': ['flower', 'plant', 'garden', 'beautiful', 'romantic', 'love', 'red', 'petals', 'thorn', 'nature', 'outdoor', 'gardening', 'bloom', 'actor', 'actress', 'rose byrne', 'hollywood', 'celebrity', 'famous', 'entertainment', 'film', 'movie', 'star', 'cast', 'theater', 'drama', 'performance'],
                    'screen': ['display', 'monitor', 'computer', 'television', 'tv', 'movie', 'film', 'entertainment', 'digital', 'electronic', 'image', 'picture', 'visual'],
                    'organ': ['music', 'instrument', 'keyboard', 'church', 'pipe', 'sound', 'melody', 'harmony', 'classical', 'concert', 'performance', 'musical', 'art'],
                    'brush': ['paint', 'art', 'artist', 'painting', 'color', 'canvas', 'creative', 'tool', 'hair', 'comb', 'grooming', 'beauty', 'makeup'],
                    'tube': ['pipe', 'cylinder', 'round', 'hollow', 'music', 'amplifier', 'sound', 'electronic', 'technology', 'transport', 'subway', 'metro', 'underground'],
                    'fighter': ['warrior', 'soldier', 'combat', 'battle', 'war', 'military', 'defense', 'attack', 'weapon', 'strength', 'courage', 'brave', 'hero'],
                    'diamond': ['gem', 'jewel', 'baseball', 'ring', 'engagement', 'valuable', 'precious', 'stone', 'mineral', 'crystal', 'sparkle', 'brilliant'],
                    'bear': ['animal', 'brown', 'polar', 'grizzly', 'teddy', 'chicago', 'stock', 'market', 'invest', 'honey', 'forest', 'wild', 'dangerous'],
                    'paris': ['france', 'eiffel', 'tower', 'french', 'europe', 'louvre', 'romance', 'city', 'capital', 'fashion', 'art', 'culture'],
                    'egypt': ['pyramid', 'cairo', 'sphinx', 'pharaoh', 'nile', 'africa', 'ancient', 'history', 'desert', 'mummy', 'tomb', 'hieroglyphics'],
                    'hollywood': ['movie', 'film', 'california', 'actor', 'cinema', 'star', 'entertainment', 'famous', 'celebrity', 'la', 'los angeles', 'showbiz'],
                    'washington': ['dc', 'president', 'george', 'capital', 'white house', 'america', 'government', 'politics', 'state', 'united', 'states']
                }
                
                # Check which team words are too close to assassin
                for card in synapse.cards:
                    if (card.color == synapse.your_team and not card.is_revealed):
                        word_lower = card.word.lower()
                        # Direct substring check
                        if (word_lower in assassin_lower or assassin_lower in word_lower):
                            dangerous_team_words.append(card.word)
                        # Association check
                        elif assassin_lower in assassin_related_terms:
                            if word_lower in assassin_related_terms[assassin_lower]:
                                dangerous_team_words.append(card.word)
                        # Reverse check - does word have assassin in its related terms?
                        elif word_lower in assassin_related_terms:
                            if assassin_lower in assassin_related_terms[word_lower]:
                                dangerous_team_words.append(card.word)
                
                dangerous_words_warning = ""
                if dangerous_team_words:
                    dangerous_words_warning = f"""
### 🚫 DANGEROUS TEAM WORDS (TOO CLOSE TO ASSASSIN):
These are YOUR team's words but they are DANGEROUSLY associated with the assassin:
{', '.join(dangerous_team_words)}

⚠️ **DO NOT give clues for these words!** Even though they're yours, the operative 
might connect them to the assassin and guess it by accident. SKIP these words entirely!
"""
                
                assassin_warning = f"""
### ⚠️ ⚠️ ⚠️ CRITICAL ASSASSIN WARNING ⚠️ ⚠️ ⚠️
The ASSASSIN word is: **{assassin_word}**

MANDATORY ASSASSIN AVOIDANCE PROTOCOL:
1. List 25+ associations with "{assassin_word}" from THESE CATEGORIES:
   a) Cultural (food, traditions, symbols, celebrations)
   b) Geographic (cities, landmarks, regions, countries)
   c) Historical (events, periods, famous moments, wars)
   d) Companies/Brands (famous businesses from that word)
   e) Industries (what is {assassin_word} famous for making/doing?)
   f) People (famous individuals, titles, roles, celebrities)
   g) Language/phrases (common expressions, idioms)
   h) Sports/Entertainment (teams, events, arts, media)
   i) Technology (related tech, inventions, innovations)
   j) Science (research, discoveries, fields)
   k) Nature (animals, plants, natural phenomena)
   l) Education (schools, subjects, academic fields)
   - Be THOROUGH - missing even ONE can lose the game!

2. NEVER use ANY of those concepts as your clue

3. **ENHANCED ASSASSIN OVERLAP TEST (CRITICAL)**:
   a) "Does my clue relate to {assassin_word}?" (e.g., CONTAINER → bottle → BOTTLE ❌)
   b) "Does {assassin_word} relate to my clue?" (e.g., BOTTLE → container → CONTAINER ❌)
   c) "Could my operative reasonably guess {assassin_word} from this clue?" (YES = REJECT)
   d) "Do ANY of my target words relate to {assassin_word}?" (e.g., PRINCESS → royalty → CROWN ❌)
   e) "Are they used together in common phrases?" (e.g., "crown jewels" ❌)
   f) Any famous companies/brands involved? (e.g., GERMANY + Lufthansa → FLIGHT ❌)
   g) If ANY answer is YES or MAYBE → REJECT clue immediately!

Examples of COMPLETE association lists (25+ each):
- GERMANY → beer, sausages, Berlin, Munich, WWII, Nazis, LUFTHANSA, BMW, Mercedes, Audi, autobahn, 
  Oktoberfest, engineering, Alps, Rhine, Bundesliga, football, lederhosen, cars, FLIGHT/aviation, 
  Volkswagen, Siemens, Bosch, Porsche, Adidas, Puma, German language, Deutsche Bank, Chancellor
- CROWN → royalty, king, queen, prince, princess, TREASURE, GEM, jewels, JEWELRY, royal, throne, gold, monarch, 
  coronation, scepter, palace, kingdom, nobility, crown jewels, regal, sovereign, heir, diadem, tiara, 
  empire, dynasty, Buckingham Palace, Windsor Castle, royal family
- CHINA → culture, Asia, Great Wall, dragon, Beijing, Shanghai, communist, tea, silk, panda, dynasty, 
  Mao, mandarin, rice, chopsticks, kung fu, red, emperor, jade, factories, trade, Confucius, Buddhism, 
  porcelain, fireworks, acupuncture, tai chi, terracotta warriors, Yangtze River, Tiananmen Square

⚠️ **CRITICAL EXAMPLES OF FAILED CLUES:**
- CROWN is assassin → "GEM" for DIAMOND + PRINCESS = ❌ LOSS (GEM → crown jewels → CROWN)
- GERMANY is assassin → "FLIGHT" for PLANE = ❌ LOSS (FLIGHT → Lufthansa → GERMANY)  
- If target word is in assassin list (e.g., PRINCESS when CROWN is assassin) → SKIP IT!

CRITICAL: Must check ALL 8 categories! Missing ANY category = potential game loss!
BETTER TO: Give a safe 1-2 word clue than a risky 3-4 word clue near the assassin!

{dangerous_words_warning}
"""
            
            # Build enhanced game history context with opponent analysis
            history_context = ""
            if game_context and (game_context.get('our_clues') or game_context.get('opponent_clues')):
                our_clues = game_context.get('our_clues', [])
                opponent_clues = game_context.get('opponent_clues', [])
                our_guesses = game_context.get('our_guesses', [])
                
                # Analyze opponent patterns
                opponent_analysis = ""
                if opponent_clues:
                    opponent_themes = []
                    for clue_data in opponent_clues:
                        if isinstance(clue_data, dict) and 'clue' in clue_data:
                            opponent_themes.append(clue_data['clue'])
                    
                    if opponent_themes:
                        opponent_analysis = f"""
### Opponent Strategy Analysis:
- Opponent themes: {', '.join(set(opponent_themes))}
- Avoid giving clues that overlap with opponent themes
- Consider if opponent is being aggressive (high numbers) or conservative (low numbers)
"""
                
                # Analyze our successful patterns
                our_patterns = ""
                if our_clues:
                    our_themes = []
                    for clue_data in our_clues:
                        if isinstance(clue_data, dict) and 'clue' in clue_data:
                            our_themes.append(clue_data['clue'])
                    
                    if our_themes:
                        our_patterns = f"""
### Our Successful Patterns:
- Our themes: {', '.join(set(our_themes))}
- Build on successful patterns, avoid repeating failed ones
- Consider thematic consistency vs. variety
"""
                
                history_context = f"""
### Enhanced Game History (Previous Turns):
- Our previous clues: {our_clues}
- Our previous guesses: {our_guesses}
- Opponent's clues: {opponent_clues}
- Use this to avoid confusing themes and to build on previous successful patterns
{opponent_analysis}
{our_patterns}
"""
            
            # Build revealed cards insight
            revealed_context = f"""
### Revealed Cards Analysis:
- Our team has found: {revealed_analysis['our_team']} ({len(revealed_analysis['our_team'])} cards)
- Opponent has found: {revealed_analysis['opponent']} ({len(revealed_analysis['opponent'])} cards)
- Neutrals hit: {revealed_analysis['neutral']}
- Likely opponent targets: {likely_opponent_words if likely_opponent_words else 'Unknown yet'}
"""
            
            strategic_context = f"""
### CRITICAL STRATEGIC NOTES:
- You are currently {position} in the game (Your cards left: {my_cards_left}, Opponent: {opponent_cards_left})
- {'Focus on SAFE, high-probability clues with lower numbers' if position == 'ahead' else 'Take calculated risks with higher numbers to catch up' if position == 'behind' else 'Balance risk and reward carefully'}
- Your clue MUST NOT match or contain any word currently on the board: {unrevealed_words}
- Triple-check that your clue word is NOT a substring or superstring of any board word
- {'IMPORTANT: You are AHEAD - use conservative numbers (1-2) to protect your lead' if position == 'ahead' else 'IMPORTANT: You are BEHIND - use higher numbers (2-4) to catch up' if position == 'behind' else 'IMPORTANT: You are TIED - balance safety with progress (1-3)'}

{assassin_warning}

{revealed_context}

{history_context}

### Additional Considerations:
- Avoid themes that could lead to opponent words: {likely_opponent_words}
- Consider what words your operative might confuse with opponent/neutral cards
- Build on successful patterns from previous clues if applicable
"""
        else:
            # Build game history for operative with incomplete clue tracking
            history_context = ""
            incomplete_clues_info = []
            
            if game_context:
                our_clues = game_context.get('our_clues', [])
                our_guesses = game_context.get('our_guesses', [])
                
                # Track incomplete clues (clues where we didn't guess all words)
                for clue in our_clues:
                    if ':' in clue:
                        clue_word, clue_num = clue.split(':')
                        clue_num = int(clue_num)
                        
                        # Count how many guesses were made after this clue
                        # (simplified: we assume sequential guessing)
                        guesses_for_clue = min(len(our_guesses), clue_num)
                        remaining = clue_num - guesses_for_clue
                        
                        if remaining > 0:
                            incomplete_clues_info.append(f"{clue_word} ({remaining} word(s) remaining)")
                
                if our_clues or our_guesses:
                    history_context = f"""
### Your Team's History This Game:
- Previous clues you received: {our_clues}
- Words you've already guessed: {our_guesses}
"""
                    if incomplete_clues_info:
                        history_context += f"""
### 🎯 INCOMPLETE CLUES - PRIORITY TARGETS:
- Incomplete clues from previous turns: {incomplete_clues_info}
- IMPORTANT: You can guess +1 BONUS word from previous clues if it's still unrevealed!
- Example: If clue was SPACE:3 and you only guessed 2, the 3rd SPACE word is still available
- Consider these incomplete clues ALONG WITH the current clue
"""
            
            # Improved confidence threshold based on position - more aggressive to reduce missed guesses
            confidence_threshold = 6 if position == 'ahead' else 5 if position == 'tied' else 4
            
            strategic_context = f"""
### CRITICAL STRATEGIC NOTES:  
- You are currently {position} in the game (Your cards left: {my_cards_left}, Opponent: {opponent_cards_left})
- Confidence threshold: Only guess words with {confidence_threshold}+ confidence (1-10 scale)
- {'Be MODERATELY conservative - prioritize high-confidence guesses' if position == 'ahead' else 'Take calculated risks to catch up' if position == 'behind' else 'Balance progress with caution'}
- ASSASSIN SAFETY: If a word has ANY assassin-like associations, skip it unless 10/10 confidence
- CRITICAL: Always check if a word could be the assassin - if uncertain, skip it
- Only guess unrevealed words: {unrevealed_words}
- Order your guesses by confidence level (most confident first)
- Consider using +1 bonus guess from previous incomplete clues when confident
- {'IMPORTANT: You are AHEAD - protect your lead with safe, high-confidence guesses' if position == 'ahead' else 'IMPORTANT: You are BEHIND - take calculated risks to catch up' if position == 'behind' else 'IMPORTANT: You are TIED - balance safety with progress'}

### ADVANCED STRATEGIC ANALYSIS:
- Game Phase: {'Early' if my_cards_left > 6 else 'Mid' if my_cards_left > 3 else 'Late'}
- Risk Level: {'Low' if position == 'ahead' else 'High' if position == 'behind' else 'Medium'}
- Optimal Strategy: {'Defensive' if position == 'ahead' else 'Aggressive' if position == 'behind' else 'Balanced'}
- Turn Priority: {'Quality over quantity' if position == 'ahead' else 'Quantity to catch up' if position == 'behind' else 'Balanced approach'}

### Revealed Cards Context:
- Your team has found: {revealed_analysis['our_team']}
- Opponent has found: {revealed_analysis['opponent']}
- Neutrals hit: {revealed_analysis['neutral']}
- Likely opponent words to AVOID: {likely_opponent_words if likely_opponent_words else 'Unknown'}

{history_context}

### Decision Framework:
For EACH potential guess, rate confidence 1-10 and only include if >= {confidence_threshold}:
- CRITICAL ASSASSIN SAFETY TEST (MANDATORY):
  * Step 1: Could this word be the assassin? (YES = IMMEDIATE REJECT)
  * Step 2: Does this word relate to the clue in a way that could also describe the assassin?
  * Step 3: Could the assassin word be a valid interpretation of this clue?
  * Step 4: Would a reasonable person connect this word to the assassin?
  * Step 5: Is this word commonly associated with the assassin? (flowers, actors, containers, etc.)
  * Step 6: ASSASSIN CONFIDENCE SCORE: Rate 1-10 how likely this could be the assassin
  * If assassin confidence >= 3/10: REJECT IMMEDIATELY
  * If ANY doubt about assassin status: SKIP IT - NEVER guess if uncertain
- Could this be opponent's word? If yes, need 9/10 confidence
- How strong is the association to the clue? Rate honestly
"""

        userPrompt = f"""
        ### Current Game State
        Your Team: {synapse.your_team}
        Your Role: {synapse.your_role}
        Red Cards Left to Guess: {synapse.remaining_red}
        Blue Cards Left to Guess: {synapse.remaining_blue}

        Board: {board}

        {clue_block}

        {strategic_context}"""
        
        messages: typing.List[typing.Dict] = []
        messages.append(
            {
                "role": "system",
                "content": (
                    spySysPrompt if synapse.your_role == "spymaster" else opSysPrompt
                ),
            }
        )
        messages.append({"role": "user", "content": userPrompt})

        async def get_gpt4_response(messages, role):
            max_retries = 3
            
            # Temperature tuning by role
            # Spymaster: Lower temp for safer, less risky clues (avoid creative assassin traps)
            # Operative: Conservative for reliable word associations
            base_temperature = 0.6 if role == "spymaster" else 0.5
            
            # Chutes.ai configuration
            use_chutes = os.environ.get("USE_CHUTES_AI", "false").lower() == "true"
            chutes_inference_url = "https://llm.chutes.ai/v1/chat/completions"
            # Default to best available model: DeepSeek-V3 or DeepSeek-R1
            chutes_model = os.environ.get("CHUTES_MODEL", "deepseek-ai/DeepSeek-V3")
            
            for attempt in range(max_retries):
                try:
                    # Reduce temperature on retries for more reliable output
                    adjusted_temperature = base_temperature * (0.85 ** attempt)
                    
                    bt.logging.debug(f"API call attempt {attempt+1}/{max_retries}, temp={adjusted_temperature:.2f}")
                    
                    if use_chutes:
                        # Use Chutes.ai NON-streaming API for reliability (streaming causes truncation)
                        bt.logging.debug(f"Using Chutes.ai model: {chutes_model}")
                        
                        headers = {
                            "Authorization": f"Bearer {os.environ.get('CHUTES_API_KEY')}",
                            "Content-Type": "application/json"
                        }
                        
                        # Increased max_tokens to prevent truncation (was 600, now 1200)
                        # Reasoning strings can be long with assassin analysis
                        body = {
                            "model": chutes_model,
                            "messages": messages,
                            "temperature": adjusted_temperature,
                            "max_tokens": 1800,  # Doubled to prevent truncation
                            "stream": False  # Non-streaming for reliability
                        }
                        
                        # Validator has 30s timeout with 3 retries, so we have ~25s per attempt
                        async with httpx.AsyncClient(timeout=25.0) as client:
                            response = await client.post(chutes_inference_url, headers=headers, json=body)
                            
                            if response.status_code != 200:
                                error_text = response.text
                                bt.logging.error(f"Chutes API request failed: {response.status_code} - {error_text}")
                                raise Exception(f"Chutes API error: {error_text}")
                            
                            response_json = response.json()
                            
                            if "choices" not in response_json or len(response_json["choices"]) == 0:
                                raise Exception("Chutes API returned no choices")
                            
                            response_text = response_json["choices"][0]["message"]["content"]
                        
                        if not response_text.strip():
                            raise Exception("Chutes API returned empty response")
                        
                        # Validate JSON is complete before returning
                        test_cleaned = response_text.strip()
                        if test_cleaned.startswith("```"):
                            first_newline = test_cleaned.find('\n')
                            if first_newline != -1:
                                test_cleaned = test_cleaned[first_newline + 1:]
                            if test_cleaned.endswith("```"):
                                test_cleaned = test_cleaned[:-3].strip()
                        
                        # Check if response is valid JSON
                        try:
                            test_json = json.loads(test_cleaned)
                            # Verify required fields exist
                            if synapse.your_role == "spymaster":
                                if "clue" not in test_json or "number" not in test_json:
                                    bt.logging.warning(f"Incomplete JSON (missing fields), retrying...")
                                    raise Exception("Incomplete JSON response")
                            else:
                                if "guesses" not in test_json:
                                    bt.logging.warning(f"Incomplete JSON (missing guesses), retrying...")
                                    raise Exception("Incomplete JSON response")
                        except json.JSONDecodeError as e:
                            bt.logging.warning(f"Invalid JSON from Chutes.ai, retrying: {e}")
                            raise Exception(f"Invalid JSON: {e}")
                        
                        return response_text
                        
                    else:
                        # Use standard OpenAI API
                        bt.logging.debug(f"Using OpenAI model: gpt-4o-mini")
                        client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
                                
                        response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=messages,
                                    temperature=adjusted_temperature,
                                    max_tokens=600,
                                    response_format={"type": "json_object"}
                        )
                        if not response.choices or len(response.choices) == 0:
                            raise Exception("OpenAI API returned no choices")
                        return response.choices[0].message.content
                        
                except json.JSONDecodeError as e:
                    bt.logging.error(f"JSON decode error on attempt {attempt+1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                except Exception as e:
                    bt.logging.error(f"Error fetching response on attempt {attempt+1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))  # Exponential backoff
                        continue
            return None

        response_str = await get_gpt4_response(messages, synapse.your_role)
        
        # Initialize default values
        clue = None
        number = None
        reasoning = None
        guesses = None
        valid = True  # Initialize clue validity flag
        
        # Robust JSON parsing with fallback
        if response_str:
            try:
                # Strip markdown code blocks if present (Chutes.ai often wraps in ```json ... ```)
                cleaned_response = response_str.strip()
                if cleaned_response.startswith("```"):
                    # Find the first newline after ```json or ```
                    first_newline = cleaned_response.find('\n')
                    if first_newline != -1:
                        cleaned_response = cleaned_response[first_newline + 1:]
                    # Remove trailing ```
                    if cleaned_response.endswith("```"):
                        cleaned_response = cleaned_response[:-3].strip()
                
                response_dict = json.loads(cleaned_response)
                
                if synapse.your_role == "spymaster":
                    clue = response_dict.get("clue")
                    number = response_dict.get("number")
                    reasoning = response_dict.get("reasoning")
                    
                    # Validate clue before sending
                    if clue:
                        is_valid = self.validate_clue(clue, unrevealed_words)
                        if not is_valid:
                            bt.logging.warning(f"Invalid clue detected: '{clue}'. Attempting safer fallback.")
                            valid = False
                            # Fallback to a very safe generic clue
                            clue = "THING"
                            number = 1
                            reasoning = "Using safe fallback clue due to validation failure"
                        else:
                            valid = True
                            bt.logging.debug(f"Clue '{clue}' validated successfully")
                    else:
                        valid = False
                        bt.logging.warning("No clue provided by LLM")
                    
                    # Ensure number is valid
                    if number:
                        number = max(1, min(int(number), len(unrevealed_words)))
                    else:
                        number = 1
                        
                else:  # operative
                    reasoning = response_dict.get("reasoning")
                    guesses_raw = response_dict.get("guesses", [])
                    
                    # Handle both list of strings and list of objects with confidence
                    guesses_with_confidence = []
                    if guesses_raw and len(guesses_raw) > 0:
                        if isinstance(guesses_raw[0], dict):
                            # Format: [{"word": "OCEAN", "confidence": 9}, ...]
                            guesses_with_confidence = guesses_raw
                        else:
                            # Format: ["OCEAN", "RIVER", ...] - assume high confidence
                            guesses_with_confidence = [{"word": g, "confidence": 8} for g in guesses_raw]
                    
                    # Determine confidence threshold based on game position
                    # Balanced approach: more aggressive to reduce missed opportunities
                    # Still safe but not overly conservative
                    confidence_threshold = 6 if position == 'ahead' else 5 if position == 'tied' else 4
                    
                    # Filter by confidence and validity
                    filtered_guesses = []
                    all_valid = True
                    for guess_obj in guesses_with_confidence:
                        word = guess_obj.get("word", guess_obj) if isinstance(guess_obj, dict) else guess_obj
                        confidence = guess_obj.get("confidence", 7) if isinstance(guess_obj, dict) else 7
                        
                        # Check if word is on board and unrevealed
                        if word not in unrevealed_words:
                            bt.logging.debug(f"Skipping invalid word: {word}")
                            all_valid = False
                            continue
                        
                        # Check confidence threshold
                        if confidence < confidence_threshold:
                            bt.logging.info(f"Skipping low confidence guess: {word} (confidence: {confidence}, threshold: {confidence_threshold})")
                            continue
                        
                        filtered_guesses.append(word)
                    
                    guesses = filtered_guesses
                    # Operative guesses are valid if we have at least some valid guesses
                    valid = len(guesses) > 0 and all_valid
                    
                    if len(filtered_guesses) != len(guesses_with_confidence):
                        bt.logging.info(f"Confidence filtering: {len(guesses_with_confidence)} -> {len(filtered_guesses)} guesses (threshold: {confidence_threshold})")
                    
                    if not guesses:
                        bt.logging.warning("No valid high-confidence guesses provided")
                        guesses = []
                        valid = True  # Empty guesses are valid (passing turn)
                        
            except json.JSONDecodeError as e:
                bt.logging.error(f"Failed to parse JSON response: {e}. Response: {response_str[:200]}")
                # Provide SMART fallback to avoid "THING:1" disaster
                if synapse.your_role == "spymaster":
                    # Pick a generic but safe clue based on unrevealed team words
                    team_words = [c.word for c in synapse.cards if c.color == synapse.your_team and not c.is_revealed]
                    if team_words:
                        # Use generic categories that might connect to something
                        generic_clues = ["OBJECT", "ITEM", "PLACE", "ACTION", "CONCEPT"]
                        clue = generic_clues[len(team_words) % len(generic_clues)]
                        number = min(2, len(team_words))  # At least try for 2
                    else:
                        clue = "THING"
                        number = 1
                    reasoning = "Fallback due to parsing error - using safe generic clue"
                    valid = True  # Fallback clues are simple but valid
                    bt.logging.warning(f"Using fallback clue: {clue}:{number}")
                else:
                    # Operative: don't guess randomly, skip turn
                    guesses = []
                    reasoning = "Fallback due to parsing error - skipping to avoid bad guess"
                    valid = True  # Passing turn is valid
            except Exception as e:
                bt.logging.error(f"Unexpected error processing response: {e}")
                if synapse.your_role == "spymaster":
                    team_words = [c.word for c in synapse.cards if c.color == synapse.your_team and not c.is_revealed]
                    if team_words:
                        generic_clues = ["OBJECT", "ITEM", "PLACE", "ACTION", "CONCEPT"]
                        clue = generic_clues[len(team_words) % len(generic_clues)]
                        number = min(2, len(team_words))
                    else:
                        clue = "THING"
                        number = 1
                    reasoning = "Fallback due to error - using safe generic clue"
                    valid = True  # Fallback clues are simple but valid
                    bt.logging.warning(f"Using fallback clue: {clue}:{number}")
                else:
                    guesses = []
                    reasoning = "Fallback due to error - skipping to avoid bad guess"
                    valid = True  # Passing turn is valid
        else:
            bt.logging.error("No response from GPT-4")
            # Safe defaults
            if synapse.your_role == "spymaster":
                clue = "THING"
                number = 1
                reasoning = "Fallback due to no response"
                valid = True  # Simple fallback is valid
            else:
                guesses = []
                reasoning = "Fallback due to no response"
                valid = True  # Passing turn is valid

        synapse.output = GameSynapseOutput(
            clue_text=clue,
            number=number,
            reasoning=reasoning,
            guesses=guesses,
            clue_validity=valid,
        )
        bt.logging.info(f"🚀 successfully get response from llm: {synapse}")
        
        # Update game history for future strategic use
        if synapse.your_role == "spymaster" and clue:
            self.update_game_history(game_id, "spymaster", clue=f"{clue}:{number}", is_our_turn=True)
            bt.logging.debug(f"Updated game history: spymaster clue '{clue}:{number}'")
        elif synapse.your_role == "operative" and guesses:
            self.update_game_history(game_id, "operative", guesses=guesses, is_our_turn=True)
            bt.logging.debug(f"Updated game history: operative guesses {guesses}")

        return synapse

    async def _blacklist(self, synapse: bt.Synapse) -> typing.Tuple[bool, str]:
        """
        Evaluates whether an incoming request should be blacklisted and ignored based on predefined security criteria.

        The blacklist function operates before the synapse data is deserialized, utilizing request headers to make
        decisions. This preemptive check is crucial to conserve resources by filtering out requests that will not
        be processed.

        Args:
            synapse (game.protocol.GameSynapse): A synapse object derived from the incoming request's headers.

        Returns:
            Tuple[bool, str]: A tuple where the first element is a boolean indicating if the synapse's hotkey is
                              blacklisted, and the second element is a string explaining the reason.

        This function serves as a security measure to prevent unnecessary processing of undesirable requests. It is
        advisable to enhance this function with checks for entity registration, validator status, and adequate stake
        before synapse data deserialization to reduce processing load.

        Suggested blacklist criteria:
        - Reject requests if the hotkey is not a registered entity in the metagraph.
        - Consider blacklisting entities that are not validators or lack sufficient stake.

        In practice, it is prudent to blacklist requests from non-validators or entities with insufficient stake.
        This can be verified using metagraph.S and metagraph.validator_permit. The sender's uid can be obtained via
        metagraph.hotkeys.index(synapse.dendrite.hotkey).

        If none of the blacklist conditions are met, the request should proceed to further processing.
        """

        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

        # TODO(developer): Define how miners should blacklist requests.
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            # Ignore requests from un-registered entities.
            bt.logging.debug(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"
        # Pass if owner of the subnet is the sender
        if uid == 0:
            bt.logging.debug(f"Not Blacklisting owner hotkey {synapse.dendrite.hotkey}")
            return False, "Owner hotkey"
        if self.config.blacklist.force_validator_permit:
            # If the config is set to force validator permit, then we should only allow requests from validators.
            if not self.metagraph.validator_permit[uid]:
                bt.logging.debug(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"
        # TODO: enable this in mainnet
        stake = self.metagraph.S[uid].item()
        if stake < self.config.blacklist.minimum_stake_requirement:
            return True, "pubkey stake below min_allowed_stake"

        bt.logging.debug(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )

        return False, "Hotkey recognized!"

    async def blacklist(
        self, synapse: game.protocol.GameSynapse
    ) -> typing.Tuple[bool, str]:
        return await self._blacklist(synapse)

    async def blacklist_ping(self, synapse: Ping) -> typing.Tuple[bool, str]:
        return await self._blacklist(synapse)

    async def priority(self, synapse: game.protocol.GameSynapse) -> float:
        """
        The priority function is responsible for determining the sequence in which requests are processed. Requests
        deemed more valuable or of higher priority are handled before others. It is crucial to carefully design your
        own priority mechanism.

        This current implementation calculates priority for incoming requests based on the stake of the calling entity
        within the metagraph.

        Args:
            synapse (game.protocol.GameSynapse): The synapse object containing metadata about the incoming request.

        Returns:
            float: A priority score calculated from the stake of the calling entity.

        Miners may receive requests from multiple entities simultaneously. This function decides which request should
        be prioritized. Higher priority values mean the request is processed sooner, while lower values mean it is
        processed later.

        Example priority logic:
        - Entities with a higher stake receive a higher priority score.
        """
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return 0.0

        # TODO(developer): Define how miners should prioritize requests.
        caller_uid = self.metagraph.hotkeys.index(
            synapse.dendrite.hotkey
        )  # Get the caller index.
        priority = float(
            self.metagraph.S[caller_uid]
        )  # Return the stake as the priority.
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}"
        )
        return priority


# This is the main function, which runs the miner.
if __name__ == "__main__":
    try:
        with Miner() as miner:
            while True:
                bt.logging.info(f"Miner running... {time.time()}")
                time.sleep(10)
    except Exception as e:
        bt.logging.error(f"Miner failed with exception: {e}")
        bt.logging.info(f"Miner exiting...")
