import random
import numpy as np
from typing import List

from pygame import font

from animate.animate import anime


class Block:
    def __init__(self, num, pos, moveType=0) -> None:
        self.num = num
        self.lastPos = pos
        self.anotherPos = [-1, -1]
        self.animate = anime((0, 0), (0, 0), 1)
        self.anotherAnimate = anime((0, 0), (0, 0), 1)
        self.moveType = moveType

    def addAnimate(self, startPos, endPos, totalTime, function=None):
        if self.animate.startPos == startPos and self.animate.endPos == endPos:
            return
        else:
            if function == None:
                self.animate = anime(startPos, endPos, totalTime)
            else:
                self.animate = anime(startPos, endPos, totalTime, function)

    def addAnotherAnimate(self, startPos, endPos, totalTime, function=None):
        if self.anotherAnimate.startPos == startPos and self.anotherAnimate.endPos == endPos:
            return
        else:
            if function == None:
                self.anotherAnimate = anime(startPos, endPos, totalTime)
            else:
                self.anotherAnimate = anime(
                    startPos, endPos, totalTime, function)

# TODO 将Broad改为任意矩形，将lineProcess归入Broad类


def lineProcess(line):  # 处理一行
    i = 0
    changed = False
    for i in range(len(line)):  # 将0聚集在尾部
        if(line[i].num == 0):
            k = i
            for j in range(i+1, len(line)):
                if(line[j].num != 0):
                    line[k] = line[j]
                    line[k].moveType = 0
                    changed = True
                    line[j] = Block(0, line[j].lastPos)
                    k += 1
            break
    for i in range(len(line)-1):  # 只需要到len-1即可，最后一位是不会合并的
        if line[i].num == 0:   # 已经将0转移至尾，如果扫到0则证明已经结束
            return line, changed
        else:
            if line[i].num == line[i+1].num:  # 如果相同则合并
                line[i+1].anotherPos = line[i].lastPos
                line[i] = line[i+1]
                line[i].moveType = 1
                line[i].num *= 2
                changed = True
                k = i+1
                for j in range(i+2, len(line)):  # 合并后将后面数据前移
                    if(line[j].num != 0):
                        line[k] = line[j]
                        line[j] = Block(0, line[j].lastPos)
                        k += 1
                if k == i+1:
                    line[i+1] = Block(0, line[i+1].lastPos)
    return line, changed


class Board:
    def __init__(self, size, map=None):
        self.size = size
        self.score = 0
        self.debug = False
        if map != None:
            for i in range(size):
                for j in range(size):
                    self.map[i][j] = Block(map[i][j].num, [i, j])
        else:
            self.map = np.array([[Block(0, [i, j])
                                  for i in range(size)] for j in range(size)])
        self.add()  # 随机产生第一个随机数
        self.add()  # 随机产生第二个随机数

    def mapPrint(self):
        for i in range(self.size):
            for j in range(self.size):
                print(self.map[j][i].num, end=' || ')
            print()
        print()

    # 新增2或4，有1/4概率产生4
    def add(self):
        while True:
            r = random.randint(0, self.size - 1)  # 随机产生一个横坐标
            c = random.randint(0, self.size - 1)  # 随机产生一个纵坐标
            if self.map[r][c].num == 0:  # 判断该坐标处是否有数值，若存在表示已有数据，重新产生随机坐标
                x = random.randint(1, 2) * 2  # 随机产生一个 2 或 4
                self.map[r][c] = Block(x, [r, c], 2)  # 设置该坐标为随机值
                break

    def add_xy(self, x, y, val):
        if self.map[x][y].num == 0:
            self.map[x][y] = Block(val, [x, y], 2)
            return True
        else:
            return False

    # 向上计算
    def move_up(self):
        changed = False
        newLines = []
        for i in range(self.size):
            tempLine, tempChanged = lineProcess(
                self.map[i, :])  # 将map拆分成line进行处理
            newLines.append(tempLine)
            changed = changed or tempChanged
        if changed > 0:  # 发生改变
            newMap = np.vstack((newLines[0], newLines[1]))
            for i in range(2, len(newLines)):
                newMap = np.vstack((newMap, newLines[i]))
            self.map = newMap
            self.add()  # 添加一个新数
        if self.debug:
            self.mapPrint()
        return self

    # 向下计算
    def move_down(self):
        changed = False
        newLines = []
        for i in range(self.size):
            tempLine, tempChanged = lineProcess(
                self.map[i, ::-1])  # 将map拆分成line进行处理
            newLines.append(tempLine)
            changed = changed or tempChanged
        if changed > 0:  # 发生改变
            newMap = np.vstack((newLines[0][::-1], newLines[1][::-1]))
            for i in range(2, len(newLines)):
                newMap = np.vstack((newMap, newLines[i][::-1]))
            self.map = newMap
            self.add()  # 添加一个新数
        if self.debug:
            self.mapPrint()
        return self

    # 向左计算
    def move_left(self):
        changed = False
        newLines = []
        for i in range(self.size):
            tempLine, tempChanged = lineProcess(
                self.map[:, i])  # 将map拆分成line进行处理
            newLines.append(tempLine)
            changed = changed or tempChanged
        if changed > 0:  # 发生改变
            newMap = np.hstack(
                (np.transpose([newLines[0]]), np.transpose([newLines[1]])))
            for i in range(2, len(newLines)):
                newMap = np.hstack((newMap, np.transpose([newLines[i]])))
            self.map = newMap
            self.add()  # 添加一个新数
        if self.debug:
            self.mapPrint()
        return self

    # 向右计算
    def move_right(self):
        changed = False
        newLines = []
        for i in range(self.size):
            tempLine, tempChanged = lineProcess(
                self.map[::-1, i])  # 将map拆分成line进行处理
            newLines.append(tempLine)
            changed = changed or tempChanged
        if changed > 0:  # 发生改变
            newMap = np.hstack(
                (np.transpose([newLines[0][::-1]]), np.transpose([newLines[1][::-1]])))
            for i in range(2, len(newLines)):
                newMap = np.hstack((newMap, np.transpose([newLines[i][::-1]])))
            self.map = newMap
            self.add()  # 添加一个新数
        if self.debug:
            self.mapPrint()
        return self

    # 判断游戏结束
    def over(self):
        # 判断数值矩阵中是否有零
        for r in range(self.size):
            for c in range(self.size):
                if self.map[r][c].num == 0:
                    return False
        # 判断是否可以左右相消
        for r in range(self.size):
            for c in range(self.size - 1):
                if self.map[r][c].num == self.map[r][c + 1].num:
                    return False
        # 判断是否可以上下相消
        for r in range(self.size - 1):
            for c in range(self.size):
                if self.map[r][c].num == self.map[r + 1][c].num:
                    return False
        # print("游戏结束")
        return True
