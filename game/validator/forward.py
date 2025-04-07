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
import bittensor as bt

from game.protocol import GameSynapse
from game.validator.reward import get_rewards
from game.utils.uids import get_random_uids
import random
import typing
from game.utils.game import GameState, Role, TeamColor, CardColor, CardType, Clue, ChatMessage
def organize_team(self, uids):
    """
    Organize the team with 4 miners randomly

    Args:
        uids (list[int]): The list of miner uids

    Returns:
        tuple[dict[str, int], dict[str, int]]: The red team and the blue team
    """
    # devide into 2 teams randomly
    team1 = {}
    team2 = {}
    for i, uid in enumerate(uids):
        if i == 0:
            team1["spymaster"] = uid
        elif i == 1:
            team1["operative"] = uid
        elif i == 2:
            team2["spymaster"] = uid
        elif i == 3:
            team2["operative"] = uid
    return team1, team2
def resetAnimations(self, cards):
    """
    Reset the animation of the cards

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.
        cards (list[CardType]): The list of cards
    """
    for card in cards:
        card.was_recently_revealed = False
async def forward(self):
    """
    This method is invoked by the validator at each time step.

    Its main function is to query the network and evaluate the responses.

    Parameters:
        self (bittensor.neuron.Neuron): The neuron instance containing all necessary state information for the validator.

    """
    # get_random_uids is an example method, but you can replace it with your own.
    # * Select 4 miners randomly and organize 2 teams
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    bt.logging.info(f"Selected miners: {miner_uids}")
    # The dendrite client queries the network.
    # organize team
    (red_team, blue_team) = organize_team(self, miner_uids)
    # # ! TODO red_team and blue_team are organized with only 1 miner for testing purposes
    # red_team = {"spymaster": 1, "operative": 1}
    # blue_team = {"spymaster": 1, "operative": 1}
    bt.logging.info(f"\033[91mRed Team: {red_team}\033[0m")
    bt.logging.info(f"\033[94mBlue Team: {blue_team}\033[0m")
    # * Initialize game
    game_step = 0
    # TODO: Add team info to the game state
    game_state = GameState()
    validator_key = self.wallet.hotkey.ss58_address
    # We will use validator_key as id of the game because one validator can only play one game at a time
    # TODO: API to report the team with the initial state
    # * Game loop until game is over
    while game_state.gameWinner is None:
        # Prepare the query
        if game_state.currentRole == Role.SPYMASTER:
            cards = game_state.cards
            if game_state.currentTeam == TeamColor.RED:
                to_uid = red_team["spymaster"]
            else:
                to_uid = blue_team["spymaster"]
        else:
            cards = [
                CardType(word=card.word, color= None, is_revealed=card.is_revealed, was_recently_revealed=card.was_recently_revealed)
                for card in game_state.cards
            ]
            if game_state.currentTeam == TeamColor.RED:
                to_uid = red_team["operative"]
            else:
                to_uid = blue_team["operative"]
            
            # Remove animation of recently revealed cards
            resetAnimations(self, game_state.cards)

        bt.logging.debug(f"cards: {cards}")

        your_team = game_state.currentTeam
        your_role = game_state.currentRole
        remaining_red = game_state.remainingRed
        remaining_blue = game_state.remainingBlue
        your_clue = game_state.currentClue.clueText if game_state.currentClue is not None else None
        your_number = game_state.currentClue.number if game_state.currentClue is not None else None

        synapse = GameSynapse(
            your_team=your_team,
            your_role=your_role,
            remaining_red=remaining_red,
            remaining_blue=remaining_blue,
            your_clue=your_clue,
            your_number=your_number,
            cards=cards,
        )

        bt.logging.info(f"⏩ Sending query to miner {to_uid}")
        responses = await self.dendrite(
            # Send the query to selected miner axons in the network.
            axons=[self.metagraph.axons[to_uid]],
            # Construct a query.
            synapse=synapse,
            # All responses have the deserialize function called on them before returning.
            # You are encouraged to define your own deserialization function.
            deserialize=True,
            timeout=10, # TODO: Update timeout limit
        )
        # TODO: handle response timeout
        if len(responses) == 0 or responses[0] is None:
            game_state.gameWinner = TeamColor.RED if game_state.currentTeam == TeamColor.BLUE else TeamColor.BLUE
            resetAnimations(self, game_state.cards)
            bt.logging.info(f"💀 No response received! Game over. Winner: {game_state.gameWinner}")
            # TODO: notify backend that game is over becaouse currentTeam didn't respond in time
            break

        if game_state.currentRole == Role.SPYMASTER:
            # * Get the clue and number from the response
            clue = responses[0].clue_text
            number = responses[0].number
            reasoning = responses[0].reasoning
            game_state.currentClue = Clue(clueText=clue, number=number)
            bt.logging.info(f"Clue: {clue}, Number: {number}")
            bt.logging.info(f"Reasoning: {reasoning}")
            game_state.chatHistory.append(ChatMessage(sender=Role.SPYMASTER, message=reasoning, team=game_state.currentTeam, cards=game_state.cards))
            game_state.currentClue.clueText = clue
            game_state.currentClue.number = number

        
        elif game_state.currentRole == Role.OPERATIVE:
            # * Get the guessed cards from the response
            guesses = responses[0].guesses
            reasoning = responses[0].reasoning
            bt.logging.info(f"Guessed cards: {guesses}")
            bt.logging.info(f"Reasoning: {reasoning}")
            # * Update the game state
            choose_assasin = False
            for guess in guesses:
                card = next((c for c in game_state.cards if c.word == guess), None)
                if card is None or card.is_revealed:
                    bt.logging.debug(f"Invalid guess: {guess}")
                    continue
                card.is_revealed = True
                card.was_recently_revealed = True
                if card.color == "red":
                    game_state.remainingRed -= 1
                elif card.color == "blue":
                    game_state.remainingBlue -= 1

                if card.color == "assassin":
                    choose_assasin = True
                    game_state.gameWinner = TeamColor.RED if game_state.currentTeam == TeamColor.BLUE else TeamColor.BLUE
                    resetAnimations(self, game_state.cards)
                    bt.logging.info(f"💀 Assassin card found! Game over. Winner: {game_state.gameWinner}")
                    # TODO: notify backend that game is over because assassin card was found
                    break
                # if the card isn't our team color, break
                # if card.color is not game_state.currentTeam:
                #     break
            if choose_assasin:
                break
            game_state.currentGuesses = guesses
            game_state.chatHistory.append(ChatMessage(sender=Role.OPERATIVE, message=reasoning, team=game_state.currentTeam, cards=game_state.cards))
            
            if game_state.remainingRed == 0:
                game_state.gameWinner = TeamColor.RED
                resetAnimations(self, game_state.cards)
                bt.logging.info(f"🎉 All red cards found! Winner: {game_state.gameWinner}")
            elif game_state.remainingBlue == 0:
                game_state.gameWinner = TeamColor.BLUE
                resetAnimations(self, game_state.cards)
                bt.logging.info(f"🎉 All blue cards found! Winner: {game_state.gameWinner}")
        
        # change the role
        game_state.previousRole = game_state.currentRole
        game_state.previousTeam = game_state.currentTeam

        if game_state.currentRole == Role.SPYMASTER:
            game_state.currentRole = Role.OPERATIVE
        else:
            game_state.currentRole = Role.SPYMASTER

            # change the team after operative moved
        
            if game_state.currentTeam == TeamColor.RED:
                game_state.currentTeam = TeamColor.BLUE
            else:
                game_state.currentTeam = TeamColor.RED
        game_step += 1
        # TODO: API to report the game state after each step
        time.sleep(2)
    # * Game over
    # TODO: API to report end of the game
    # # Adjust the scores based on responses from miners.
    rewards = get_rewards(self, winner = game_state.gameWinner, red_team = red_team, blue_team = blue_team)

    bt.logging.info(f"Scored responses: {rewards}")
    # Update the scores based on the rewards. You may want to define your own update_scores function for custom behavior.
    self.update_scores(rewards, miner_uids)

    time.sleep(10)
