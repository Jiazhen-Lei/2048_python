import pickle

from interface import myStep
from board import Board
import torch                                    # 导入torch
import torch.nn as nn                           # 导入torch.nn
import torch.nn.functional as F                 # 导入torch.nn.functional
import numpy as np                              # 导入numpy
import sys
import os
import random
import time
from torch.utils.tensorboard import SummaryWriter

sys.path.append("..")


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 超参数
BATCH_SIZE = 1024                                 # 样本数量
LR = 0.01                                       # 学习率
EPSILON = 0.9                                   # greedy policy
GAMMA = 0.9                                     # reward discount
TARGET_REPLACE_ITER = 100                       # 目标网络更新频率
MEMORY_CAPACITY = 6000                          # 记忆库容量

# 使用gym库中的环境：CartPole，且打开封装(若想了解该环境，请自行百度)
# env = gym.make('CartPole-v0').unwrapped
# N_ACTIONS = env.action_space.n                  # 杆子动作个数 (2个)
# N_STATES = env.observation_space.shape[0]       # 杆子状态个数 (4个)
N_ACTIONS = 4  # 动作数4个
N_STATES = 16  # 状态数4*4=16个

"""
torch.nn是专门为神经网络设计的模块化接口。nn构建于Autograd之上，可以用来定义和运行神经网络。
nn.Module是nn中十分重要的类，包含网络各层的定义及forward方法。
定义网络：
    需要继承nn.Module类，并实现forward方法。
    一般把网络中具有可学习参数的层放在构造函数__init__()中。
    只要在nn.Module的子类中定义了forward函数，backward函数就会被自动实现(利用Autograd)。
"""


# 定义Net类 (定义网络)
class FCNet(nn.Module):
    # 定义Net的一系列属性
    def __init__(self):
        # nn.Module的子类函数必须在构造函数中执行父类的构造函数
        # 等价与nn.Module.__init__()
        super(FCNet, self).__init__()

        # 设置第一个全连接层(输入层到隐藏层): 状态数个神经元到50个神经元
        self.fc1 = nn.Linear(N_STATES, 64)
        # 权重初始化 (均值为0，方差为0.1的正态分布)
        self.fc1.weight.data.normal_(0, 0.1)
        self.fc2 = nn.Linear(64, 64)
        # 权重初始化 (均值为0，方差为0.1的正态分布)
        self.fc2.weight.data.normal_(0, 0.1)
        self.out = nn.Linear(64, N_ACTIONS)
        # 权重初始化 (均值为0，方差为0.1的正态分布)
        self.out.weight.data.normal_(0, 0.1)

    # 定义forward函数 (x为状态)
    def forward(self, x):
        x = x.view(x.size(0), -1)
        # 连接输入层到隐藏层，且使用激励函数ReLU来处理经过隐藏层后的值
        x = x.to(device)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        # x = F.relu(self.fc3(x))
        # 连接隐藏层到输出层，获得最终的输出值 (即动作值)
        actions_value = self.out(x)
        return actions_value                                                    # 返回动作值


class CNN_Net(nn.Module):
    def __init__(self, input_len, output_num, conv_size=(32, 64), fc_size=(1024, 128), out_softmax=False):
        super(CNN_Net, self).__init__()
        self.input_len = input_len
        self.output_num = output_num
        self.out_softmax = out_softmax

        self.conv1 = nn.Conv2d(
            in_channels=1, out_channels=conv_size[0], kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(
            in_channels=conv_size[0], out_channels=conv_size[1], kernel_size=3, stride=1, padding=1)

        self.fc1 = nn.Linear(conv_size[1] * self.input_len, fc_size[0])
        self.fc2 = nn.Linear(fc_size[0], fc_size[1])
        self.head = nn.Linear(fc_size[1], self.output_num)

    def forward(self, x):
        # x = x.reshape(-1, 1, self.input_len, self.input_len)

        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))

        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))

        output = self.head(x)
        if self.out_softmax:
            output = F.softmax(output, dim=1)  # 值函数估计不应该有softmax
        return output

# 定义DQN类 (定义两个网络)


class DQN(object):
    # 定义DQN的一系列属性
    def __init__(self, device=torch.device('cpu'), logPath='./'):
        self.device = device
        # 利用Net创建两个神经网络: 评估网络和目标网络
        # self.eval_net, self.target_net = FCNet().to(self.device), FCNet().to(self.device)
        self.eval_net, self.target_net = CNN_Net(N_STATES, N_ACTIONS).to(self.device), CNN_Net(N_STATES, N_ACTIONS).to(self.device)
        # for target updating
        self.learn_step_counter = 0
        # for storing memory
        self.memory_counter = 0
        # 初始化记忆库，一行代表一个transition
        self.memory = [0]*MEMORY_CAPACITY
        self.optimizer = torch.optim.Adam(
            self.eval_net.parameters(), lr=LR)    # 使用Adam优化器 (输入为评估网络的参数和学习率)
        # 使用均方损失函数 (loss(xi, yi)=(xi-yi)^2)
        self.loss_func = nn.MSELoss()
        self.logWriter = SummaryWriter('./log/%d' % (time.time()))

    # 定义动作选择函数 (x为状态)
    def choose_action(self, x):
        # 将x转换成32-bit floating point形式，并在dim=0增加维数为1的维度
        x = torch.unsqueeze(torch.FloatTensor(x), 0)
        x = torch.unsqueeze(torch.FloatTensor(x), 0).to(self.device)
        # 生成一个在[0, 1)内的随机数，如果小于EPSILON，选择最优动作
        if np.random.uniform() < EPSILON:
            # 通过对评估网络输入状态x，前向传播获得动作值
            actions_value = self.eval_net.forward(x)
            # 输出每一行最大值的索引，并转化为numpy ndarray形式
            action = torch.max(actions_value, 1)[1].data.cpu().numpy()
            # 输出action的第一个数
            action = action[0]
        else:                                                                   # 随机选择动作
            # 这里action随机等于0或1 (N_ACTIONS = 2)
            action = np.random.randint(0, N_ACTIONS)
        # 返回选择的动作 (0或1)
        return action

    # 定义记忆存储函数 (这里输入为一个transition)
    def store_transition(self, s, a, r, s_):
        # 在水平方向上拼接数组
        transition = [s, [a, r], s_]
        # 如果记忆库满了，便覆盖旧的数据
        # 获取transition要置入的行数
        index = self.memory_counter % MEMORY_CAPACITY
        # 置入transition
        self.memory[index] = transition
        # memory_counter自加1
        self.memory_counter += 1

    # 定义学习函数(记忆库已满后便开始学习)
    def learn(self):
        # 目标网络参数更新
        if self.learn_step_counter % TARGET_REPLACE_ITER == 0:                  # 一开始触发，然后每100步触发
            self.target_net.load_state_dict(
                self.eval_net.state_dict())         # 将评估网络的参数赋给目标网络
        self.learn_step_counter += 1                                            # 学习步数自加1

        # 抽取记忆库中的批数据
        # 在[0, 2000)内随机抽取32个数，可能会重复
        sample_index = np.random.choice(MEMORY_CAPACITY, BATCH_SIZE)
        # 抽取32个索引对应的32个transition，存入b_memory
        # b_memory = self.memory[sample_index]
        b_memory = random.choices(self.memory, k=BATCH_SIZE)
        b_s = torch.FloatTensor([b_memory[i][0]
                                for i in range(len(b_memory))]).to(self.device)
        b_s = torch.unsqueeze(b_s, 1)
        # 将32个s抽出，转为32-bit floating point形式，并存储到b_s中，b_s为32行4列
        b_a = torch.LongTensor([[int(b_memory[i][1][0])]
                               for i in range(len(b_memory))]).to(self.device)
        # 将32个a抽出，转为64-bit integer (signed)形式，并存储到b_a中 (之所以为LongTensor类型，是为了方便后面torch.gather的使用)，b_a为32行1列
        b_r = torch.FloatTensor([[int(b_memory[i][1][1])]
                                for i in range(len(b_memory))]).to(self.device)
        # 将32个r抽出，转为32-bit floating point形式，并存储到b_s中，b_r为32行1列
        b_s_ = torch.FloatTensor([b_memory[i][2]
                                 for i in range(len(b_memory))]).to(self.device)
        b_s_ = torch.unsqueeze(b_s_, 1)
        # 将32个s_抽出，转为32-bit floating point形式，并存储到b_s中，b_s_为32行4列
        # 获取32个transition的评估值和目标值，并利用损失函数和优化器进行评估网络参数更新

        q_eval = self.eval_net(b_s).gather(1, b_a)
        # eval_net(b_s)通过评估网络输出32行每个b_s对应的一系列动作值，然后.gather(1, b_a)代表对每行对应索引b_a的Q值提取进行聚合
        q_next = self.target_net(b_s_).detach()
        # q_next不进行反向传递误差，所以detach；q_next表示通过目标网络输出32行每个b_s_对应的一系列动作值
        q_target = b_r + GAMMA * q_next.max(1)[0].view(BATCH_SIZE, 1)
        # q_next.max(1)[0]表示只返回每一行的最大值，不返回索引(长度为32的一维张量)；.view()表示把前面所得到的一维张量变成(BATCH_SIZE, 1)的形状；最终通过公式得到目标值
        loss = self.loss_func(q_eval, q_target)
        # 输入32个评估值和32个目标值，使用均方损失函数
        self.optimizer.zero_grad()                                      # 清空上一步的残余更新参数值
        # 误差反向传播, 计算参数更新值
        loss.backward()
        self.optimizer.step()                                           # 更新评估网络的所有参数

        self.logWriter.add_scalar('loss', loss, self.learn_step_counter)


if __name__ == '__main__':
    logPath = './log/%d' % (time.time())
    os.mkdir(logPath)

    # 令dqn=DQN类
    dqn = DQN(device=device, logPath=logPath)

    maxScore = 0
    maxNum = 0

    # 400个episode循环
    for i in range(400):
        print('<<<<<<<<<Episode: %s' % i)
        # 重置环境
        env = Board(4)
        # 初始化该循环对应的episode的总奖励
        episode_reward_sum = 0

        if i % 50 == 0 and i != 0:
            if maxNum >= 128:
                torch.save(dqn.target_net.state_dict(), logPath +
                           '/num%d-t%d' % (maxNum, time.time()))
        # 开始一个episode (每一个循环代表一步)
        while True:
            if maxScore < env.score:
                maxScore = env.score
            os.system("cls")
            env.mapPrint()                                                    # 显示实验动画
            # 输入该步对应的状态s，选择动作
            s = env.numMap()
            a = dqn.choose_action(s)
            # 执行动作，获得反馈
            s_, r, over, tempMaxNum = myStep(env, a)
            if tempMaxNum > maxNum:
                maxNum = tempMaxNum
            print('action:', a, 'maxScore', maxScore, 'maxNum', maxNum, 'reward:', r,
                  'score:', env.score, '\nepisode:', i, 'dqn.memory_counter:', dqn.memory_counter)

            # 修改奖励 (不修改也可以，修改奖励只是为了更快地得到训练好的摆杆)
            # x, x_dot, theta, theta_dot = s_
            # r1 = (env.x_threshold - abs(x)) / env.x_threshold - 0.8
            # r2 = (env.theta_threshold_radians - abs(theta)) / \
            #     env.theta_threshold_radians - 0.5
            # new_r = r1 + r2

            new_r = r

            dqn.store_transition(s, a, new_r, s_)                 # 存储样本
            # 逐步加上一个episode内每个step的reward
            episode_reward_sum += new_r

            # s = s_                                                # 更新状态
            # 因为我的myStep中相当于已经更新过s了所以这里注释掉

            if dqn.memory_counter > MEMORY_CAPACITY:              # 如果累计的transition数量超过了记忆库的固定容量2000
                # 开始学习 (抽取记忆，即32个transition，并对评估网络参数进行更新，并在开始学习后每隔100次将评估网络的参数赋给目标网络)
                dqn.learn()

            if over:       # 如果over为True
                # round()方法返回episode_reward_sum的小数点四舍五入到2个数字
                print('episode%s---reward_sum: %s' %
                      (i, round(episode_reward_sum, 2)))

                dqn.logWriter.add_scalar('score', env.score, i)
                dqn.logWriter.add_scalar(
                    'episode_reward_sum', episode_reward_sum, i)
                break                                             # 该episode结束