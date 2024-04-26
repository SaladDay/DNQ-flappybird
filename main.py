import pdb
import cv2
import sys
import os
sys.path.append("game/")
import wrapped_flappy_bird as game
import random
import numpy as np
from collections import deque
import torch
from torch.autograd import Variable
import torch.nn as nn

GAME = 'bird' # the name of the game being played for log files
ACTIONS = 2 # number of valid actions
GAMMA = 0.99 # decay rate of past observations
OBSERVE = 1000. # timesteps to observe before training
EXPLORE = 2000000. # frames over which to anneal epsilon
FINAL_EPSILON = 0.0001 # final value of epsilon
# INITIAL_EPSILON = 0.0001 # starting value of epsilon
INITIAL_EPSILON = 0.001
REPLAY_MEMORY = 50000 # number of previous transitions to remember
BATCH_SIZE = 32 # size of minibatch
FRAME_PER_ACTION = 1
UPDATE_TIME = 100
width = 80
height = 80

def preprocess(observation):
    # 缩放、灰度
    observation = cv2.cvtColor(cv2.resize(observation, (80, 80)), cv2.COLOR_BGR2GRAY)
    # 二值化处理
    ret, observation = cv2.threshold(observation,1,255,cv2.THRESH_BINARY)
    return np.reshape(observation, (1,80,80))

# 出一个两维数组，第一维是batch_size。第二维是动作集合大小，每个元素代表一个动作的Q值
class DeepNetWork(nn.Module):
    def __init__(self,):
        super(DeepNetWork,self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels=4, out_channels=32, kernel_size=8, stride=4, padding=2),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(in_channels=32, out_channels=64, kernel_size=4, stride=2, padding=1),
            nn.ReLU(inplace=True)
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(in_channels=64, out_channels=64, kernel_size=3, stride=1, padding=1),
            nn.ReLU(inplace=True)
        )
        self.fc1 = nn.Sequential(
            nn.Linear(1600,256),
            nn.ReLU()
        )
        self.out = nn.Linear(256,2)

    def forward(self, x):
        x = self.conv1(x); x = self.conv2(x);
        x = self.conv3(x); x = x.view(x.size(0),-1)
        x = self.fc1(x); return self.out(x)


class DQNMain(object):
    def save(self):
        print("save model param")
        torch.save(self.Q_net.state_dict(), 'params3.pth')

    def load(self):
        if os.path.exists("params3.pth"):
            print("load model param")
            self.Q_net.load_state_dict(torch.load('params3.pth'))
            self.Q_netT.load_state_dict(torch.load('params3.pth'))

    def __init__(self,actions):
        # 存储过去的经验，即先前的状态、动作、奖励和新状态的组合。这些经验被用于训练过程中的样本抽取，支持网络学习以前遇到的各种情形,
        self.replayMemory = deque() 
        self.timeStep = 0
        self.epsilon = INITIAL_EPSILON
        self.actions = actions
        self.Q_net=DeepNetWork()
        self.Q_netT=DeepNetWork()
        self.load()
        self.loss_func=nn.MSELoss()
        LR=1e-6
        self.optimizer = torch.optim.Adam(self.Q_net.parameters(), lr=LR)

    def train(self): 
        # Step 1: obtain random minibatch from replay memory
        minibatch = random.sample(self.replayMemory, BATCH_SIZE)
        state_batch = [data[0] for data in minibatch]
        action_batch = [data[1] for data in minibatch]
        reward_batch = [data[2] for data in minibatch]
        nextState_batch = [data[3] for data in minibatch] 
        # Step 2: calculate y
        y_batch = np.zeros([BATCH_SIZE,1])
        nextState_batch=np.array(nextState_batch) 
        #print("train next state shape")
        #print(nextState_batch.shape)
        nextState_batch=torch.Tensor(nextState_batch)
        action_batch=np.array(action_batch)
        index=action_batch.argmax(axis=1)
        print("action "+str(index))
        index=np.reshape(index,[BATCH_SIZE,1])
        action_batch_tensor=torch.LongTensor(index)
        QValue_batch = self.Q_netT(nextState_batch)
        QValue_batch=QValue_batch.detach().numpy()

        for i in range(0, BATCH_SIZE):
            terminal = minibatch[i][4]
            if terminal:
                y_batch[i][0]=reward_batch[i]
            else:
                # 这里的QValue_batch[i]为数组，大小为所有动作集合大小，QValue_batch[i],代表
                # 做所有动作的Q值数组，y计算为如果游戏停止，y=rewaerd[i],如果没停止，则y=reward[i]+gamma*np.max(Qvalue[i])
                # 代表当前y值为当前reward+未来预期最大值*gamma(gamma:经验系数)
                y_batch[i][0]=reward_batch[i] + GAMMA * np.max(QValue_batch[i])

        y_batch=np.array(y_batch)
        y_batch=np.reshape(y_batch,[BATCH_SIZE,1])
        state_batch_tensor=Variable(torch.Tensor(state_batch))
        y_batch_tensor=Variable(torch.Tensor(y_batch))
        y_predict=self.Q_net(state_batch_tensor).gather(1,action_batch_tensor)
        loss=self.loss_func(y_predict,y_batch_tensor)
        print("loss is "+str(loss))
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        if self.timeStep % UPDATE_TIME == 0:
            self.Q_netT.load_state_dict(self.Q_net.state_dict())
            self.save()

    def setPerception(self,nextObservation,action,reward,terminal): 
        # 用于更新环境状态、记录动作和它们的结果，并根据这些信息调整学习过程
        newState = np.append(self.currentState[1:,:,:],nextObservation,axis = 0) 
        # newState = np.append(nextObservation,self.currentState[:,:,1:],axis = 2)
        self.replayMemory.append((self.currentState,action,reward,newState,terminal))
        if len(self.replayMemory) > REPLAY_MEMORY:
            # 移除最老的经验
            self.replayMemory.popleft()
        if self.timeStep > OBSERVE: # Train the network
            self.train()

        # print info
        state = ""
        if self.timeStep <= OBSERVE:
            state = "observe"
        elif self.timeStep > OBSERVE and self.timeStep <= OBSERVE + EXPLORE:
            state = "explore"
        else:
            state = "train"
        print ("TIMESTEP", self.timeStep, "/ STATE", state, "/ EPSILON", self.epsilon)
        self.currentState = newState
        self.timeStep += 1

    def getAction(self):
        currentState = torch.Tensor([self.currentState])
        QValue = self.Q_net(currentState)[0]
        action = np.zeros(self.actions)
        if self.timeStep % FRAME_PER_ACTION == 0:
            if random.random() <= self.epsilon:
                action_index = random.randrange(self.actions)
                print("choose random action " + str(action_index))
                action[action_index] = 1
            else:
                action_index = np.argmax(QValue.detach().numpy())
                print("choose qnet value action " + str(action_index))
                action[action_index] = 1
        else:
            action[0] = 1  # do nothing

        # change episilon
        if self.epsilon > FINAL_EPSILON and self.timeStep > OBSERVE:
            self.epsilon -= (INITIAL_EPSILON - FINAL_EPSILON) / EXPLORE
        return action

    def setInitState(self, observation):
        self.currentState = np.stack((observation, observation, observation, observation),axis=0)
        print(self.currentState.shape)

if __name__ == '__main__': 
    # Step 1: init BrainDQN
    actions = 2
    brain = DQNMain(actions) # Step 2: init Flappy Bird Game
    flappyBird = game.GameState() # Step 3: play game
    # Step 3.1: obtain init state
    action0 = np.array([1,0]) # do nothing
    observation0, reward0, terminal = flappyBird.frame_step(action0)
    observation0 = cv2.cvtColor(cv2.resize(observation0, (80, 80)), cv2.COLOR_BGR2GRAY)
    ret, observation0 = cv2.threshold(observation0,1,255,cv2.THRESH_BINARY)
    brain.setInitState(observation0)
    print(brain.currentState.shape) # Step 3.2: run the game

    while 1!= 0:
        action = brain.getAction()
        nextObservation,reward,terminal = flappyBird.frame_step(action)
        nextObservation = preprocess(nextObservation)
        #print(nextObservation.shape)
        brain.setPerception(nextObservation,action,reward,terminal)
