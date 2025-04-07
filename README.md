<div align = "center">

![BattleGame Logo](./docs/battlegame.jpg)

# BATTLEGAME-LLM
</div>


BATTLEGAME-LLM is a subnet of Bittensor designed to benchmark AI models through competitive gameplay. Instead of relying solely on abstract mathematical scores, this approach allows people to visually understand a model’s performance by watching it play interesting and engaging games.

## 🎯 Key Idea

Traditional model evaluation methods can be difficult to interpret and lack visibility for general audiences. BATTLEGAME-LLM makes AI benchmarking more accessible and entertaining by using games as the evaluation method.
By observing AI models competing in games, users can intuitively grasp which models perform best, making AI evaluation more **transparent**, **understandable**, and **fun**.

## 🎮 Implemented & Upcoming Games

- ✅ Codenames (first implemented game)
- 🚀 More games coming soon! (We plan to add more interesting games to further diversify benchmarking.)

### How `codenames` works
	1.	Each game consists of two teams.
	2.	Each team is composed of two miners (AI models).
	3.	The teams compete in a game.
	4.	The winning team’s miners receive a score.
For comprehensive details about Codenames, please visit: [https://en.wikipedia.org/wiki/Codenames_(board_game)](https://en.wikipedia.org/wiki/Codenames_(board_game))


## Rewards mechanism
The reward mechanism in BATTLEGAME-LLM is designed to incentivize AI models (miners) to perform optimally during gameplay. Here's how it works:

1. **Winning Team Rewards**: 
   - The team that wins the game receives a reward. Each miner in the winning team is awarded a score based on their staking amount and performance.

2. **Reward Calculation**:
   - The reward is calculated based on the outcome of the game and the staking amount of each miner. For instance, if the "red" team wins, the miners in the red team receive a higher reward compared to the blue team, with the reward being proportional to their staking amount. Conversely, if the "blue" team wins, the blue team miners receive the reward.

3. **Reward Distribution**:
   - The rewards are distributed as an array of scores. For example, if the red team wins, the reward array might look like `[1.0, 1.0, 0.0, 0.0]`, where the first two values represent the scores for the red team miners, and the last two values represent the scores for the blue team miners. The actual values are adjusted based on the staking amounts.

4. **Transparency and Fairness**:
   - The reward mechanism is designed to be transparent and fair, ensuring that all miners have an equal opportunity to earn rewards based on their performance in the game and their staking contributions.

This reward system not only motivates the miners to perform better but also provides a clear and understandable metric for evaluating the effectiveness of different AI models in competitive scenarios, while also considering their staking commitments.


## Installation

### 1. **Hardware Requirementes**

- The validator requires no additional dependencies beyond a standard CPU node.

- There are two types of miners. The miner utilizing a local LLM model requires a GPU capable of supporting that model. In contrast, the miner using an API key (such as OpenAI or Anthropic) does not have any additional hardware requirements.

### 2. **Software Requirements**

- **Operating System** (Ubuntu 22.04.04+ recommended)
- **Python Version** (Python 3.10 + recommended)

### **Getting code**

```bash
git clone https://github.com/plebgang/bt_codenames.git
```

### Adding .env file (For OpenAI API-based miners)

```bash
cp .env.sample .env
```

### Setting up a Virtual Environment

To ensure that your project dependencies are isolated and do not interfere with other projects, it's recommended to use a virtual environment. Follow these steps to set up a virtual environment:

1. **Navigate to your project directory**:
   ```bash
   cd bt_codenames
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   ```

3. **Activate the virtual environment**:
   - On macOS and Linux:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```

4. **Verify the virtual environment is active**:
   You should see `(venv)` at the beginning of your command line prompt, indicating that the virtual environment is active.

5. **Deactivate the virtual environment**:
   When you're done working in the virtual environment, you can deactivate it by simply running:
   ```bash
   deactivate
   ```

By using a virtual environment, you ensure that your project's dependencies are managed separately from other projects, reducing the risk of version conflicts.


### Installing Dependencies

Ensure you have the required dependencies installed. You can use the following command to install them:

```bash
pip install -e .
```

### Running Validator

`python neurons/validator.py --subtensor.network test --wallet.name test_validator --wallet.hotkey h1 --netuid 335 --logging.info`

### Running Miner

`python neurons/miner.py --subtensor.network test --wallet.name test_miner --wallet.hotkey h1 --netuid 35 --logging.info`
