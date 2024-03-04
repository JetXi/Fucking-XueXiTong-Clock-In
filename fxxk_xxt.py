### 学习通位置签到程序

import json
import random
import re
import sys
import time
import requests
import urllib3
from lxml import etree
from pyDes import des, ECB, PAD_PKCS5
import binascii

"""
签到学生信息
用户名 密码 姓名 uid 地址 纬度 经度
扫描间隔时间
配置账号密码、stuname为真实姓名、address为详细地址、latitude为维度，longitude为经度（经纬度建议小数点后六位）、uid留空
"""
userinfo = {
    'username': '11111111111',
    'password': 'fuckchaoxingxxt',
    'stuname': '你好',
    'uid': '',
    'address': '江西省南昌市青山湖区江西财经大学',
    'latitude': '99.999999',
    'longitude': '999.999999',
    'conf': {
        'scan_gap_time': 60,
    }
}

"""
api列表
"""
# 登录接口 POST 无需cookie 获取cookie
# 带上账号和des加密密码，t和refer也不能少
login_url = 'https://passport2-api.chaoxing.com/fanyalogin'
# 预请求，规避自动签到的手段
pre_sign_api = 'https://mobilelearn.chaoxing.com/newsign/preSign?courseId=226359028&classId=58665851&general=1&sys=1&ls=1&appType=15&&tid=&ut=s&activePrimaryId='
# 签到接口
sign_api = 'https://mobilelearn.chaoxing.com/pptSign/stuSignajax'
# 推送服务（大家使用的服务都不一样 自己配置吧）
# push_api = 'http://wxpusher.zjiecode.com/demo/send/custom/{token}?content='
# 全局使用的头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Referer': r'http://passport2.chaoxing.com/login?fid=&newversion=true&refer=http%3A%2F%2Fi.chaoxing.com'
}

# 禁用warning
urllib3.disable_warnings()
session = requests.session()


# 获取13位时间戳
def get_timestamp():
    return str(int(time.time() * 1000))


# 伪造登录DES密钥
def DES_crypt(str):
    # 超星源码里的私钥，截取前8位（des要求八位密钥，即源码密钥八位之后废）
    secret_key = 'u2oh6Vu^'
    iv = secret_key
    k = des(secret_key, ECB, iv, pad=None, padmode=PAD_PKCS5)
    encrypt = k.encrypt(str, padmode=PAD_PKCS5)
    return binascii.b2a_hex(encrypt).decode()


# 账号密码登录、获取cookie、uid
def login_with_up_and_get_cookie():
    encryptPass = DES_crypt(userinfo['password'])
    # post数据包
    login_data = {
        'uname': userinfo['username'],
        'password': encryptPass,
        'refer': 'https%253A%252F%252Fmooc2-ans.chaoxing.com%252Fmycourse%252Fstu%253Fcourseid%253D226359028%2526clazzid%253D58665851%2526cpi%253D94321004%2526enc%253Dbd8d3d8b1373f359feec8d669d25f4d1%2526t%253D1655090749697%2526pageHeader%253D0',
        't': 'true'
    }
    session.post(login_url, headers=headers, data=login_data, verify=False)
    # print("======cookie_dict:", session.cookies)
    # 判断是否登陆成功，同时把uid拿出来，签到的时候要提交
    if 'UID' in str(session.cookies):
        # 登录成功
        print(f'---———— 登录成功!  姓名:{userinfo["stuname"]} ——————-')
        userinfo['uid'] = re.findall('<Cookie UID=(.*?) for .chaoxing.com/>', str(session.cookies))[0]
    else:
        print('登录失败')
        sys.exit()



"""
获取群和班级ID
courseId classId
::return    name_list 课程名列表
::return    courseid_list
::return    classid_list
"""
def get_course_class_id():
    url = 'http://mooc1-2.chaoxing.com/visit/courses'
    res = session.get(url, headers=headers)
    if res.status_code == 200:
        name_list, courseid_list, classid_list = [], [], []
        class_HTML = etree.HTML(res.text)
        for class_item in class_HTML.xpath("/html/body/div/div[2]/div[3]/ul/li[@class='courseItem curFile']"):
            name_list.append(class_item.xpath("./div[2]/h3/a/@title")[0])
            courseid_list.append(class_item.xpath("./input[@name='courseId']/@value")[0])
            classid_list.append(class_item.xpath("./input[@name='classId']/@value")[0])
        # 确保获取到了数据
        if name_list and courseid_list and classid_list:
            return name_list, courseid_list, classid_list
    else:
        print("error:课程处理失败")



"""
获取签到任务
保留在签到时间范围内的签到活动 如："startTime":1655089368000,"endTime":1655091168000
::return    name 课程名，便于输出日志
::return    lastet_sign['id'] 有新的签到任务,返回其id; False 没有新任务,继续扫描
::return    sign_type 签到的类型 0普通 3手势 4位置
"""
def get_sign_list(name_list, courseid_list, classid_list):
    now_time = get_timestamp()
    # 挨个扫描所有课程的签到活动 url带上当前13位时间戳
    for name, course, class_ in zip(name_list, courseid_list, classid_list):
        print(f'--- {name}扫描中！', end="")
        slapi = f'https://mobilelearn.chaoxing.com/v2/apis/active/student/activelist?fid=0&courseId={course}&classId={class_}&showNotStartedActive=0&_={get_timestamp()}'
        resp = session.get(slapi)
        loads = json.loads(resp.text)
        # 尝试获取最新的签到活动（有些课程一个活动都没有，会list out of range，直接continue跳过这类课程）
        try: latest_sign = loads['data']['activeList'][0]
        except:
            # 如果没有签到任务，就返回False，下一步继续扫描
            print(f'  暂未检测到签到任务  下一次扫描将于{userinfo["conf"]["scan_gap_time"]}秒后开始！ ---')
            continue
        # 处理230227问题：通知导致签到失败  有activeType=45即跳过，没有则继续
        try:
            if latest_sign['activeType'] == 45:
                print(f'  暂未检测到签到任务  下一次扫描将于{userinfo["conf"]["scan_gap_time"]}秒后开始！ ---')
                continue
        except: pass
        # 如果有在有效期内的签到任务，就把课程名和id返回去，下一步直接进行签到
        # 230308: 手动结束时右时间戳为空字符串  右时间戳为空时，判断距离左时间戳过了多久,30分钟内为有效
        # if not latest_sign['endTime']:
        #     if int(now_time)-latest_sign['startTime'] < 1800000:
        #         pass
        # else if latest_sign['startTime'] < int(now_time) < latest_sign['endTime']:
        #     sign_type = int(latest_sign['otherId'])
        #     print(f"  检测到一个签到任务!  任务名:{latest_sign['nameOne']}  任务ID:{latest_sign['id']}  {latest_sign['nameFour']} ---")
        #     # id签到要用
        #     return name, str(latest_sign['id']), sign_type
        # 可见手动结束引入后给判断增加了很多麻烦，故统一采用左时间戳与当前时间对比的方式，半小时内为有效活动
        if int(now_time)-latest_sign['startTime'] < 1800000:
            sign_type = int(latest_sign['otherId'])
            print(f"  检测到一个签到任务!  任务名:{latest_sign['nameOne']}  任务ID:{latest_sign['id']}  {latest_sign['nameFour']} ---")
            # id签到要用
            return name, str(latest_sign['id']), sign_type
        # 有活动且不是通知，但是不在有效期内
        else:
            print(f'  暂未检测到签到任务  下一次扫描将于{userinfo["conf"]["scan_gap_time"]}秒后开始！ ---')
    # 一轮扫描结束后如果没有发生return（即这一轮没有找到签到活动），直接返回False
    return False, False, False


"""
签到逻辑
根据signType来判断签到的类型
实际处理时并不像签到的种类一样繁琐，只需区分位置签到和其他签到
换言之，签到码二维码等方式在后端一律视为普通签到，仅有前端校验
"""
def sign(name, signID, sign_type):
    # 默认参数，用于位置签到以外的签到类型
    params = {
        'name': userinfo['stuname'],
        'activeId': signID,
        'uid': userinfo['uid'],
        'clientip': '',
        'fid': 10306,
        'appType': 15,
        'ifTiJiao': 1
    }
    # 4为位置签到，追加经纬度和地址信息
    if sign_type == 4:
        params['address'] = userinfo['address']
        params['latitude'] = userinfo['latitude']
        params['longitude'] = userinfo['longitude']
    # 最多尝试签到100次，直至成功
    for i in range(100):
        # 提交签到包之前要先presign，不然非法请求
        session.get(pre_sign_api + signID)
        # 可以放心大胆的为所欲为了
        resp = session.get(sign_api, params=params)
        # 签到成功
        if 'success' in resp.text:
            print(f'--- 第{i+1}次尝试签到... 签到成功!  课程名:{name}  任务ID:{signID} ---')
            # requests.get(f'{push_api}{userinfo["stuname"]}{name}签到成功')
            break
        # 已经签过（处理第二个定时器）
        elif '签到过了' in resp.text:
            print(f'--- 已签  课程名:{name}  任务ID:{signID} ---')
            break
        # 如果100次全部失败，推送失败消息
        elif i == 99:
            print(f'第100次尝试签到...  课程名:{name}签到失败! 停止尝试')
            # requests.get(f'{push_api}{userinfo["stuname"]}{name}签到失败')
        else:
            print(f'第{i+1}次尝试签到...  课程名:{name}签到失败! 2秒后继续尝试')
        time.sleep(2)


# 云函数懒得改了
def main_handler(a, b):
    login_with_up_and_get_cookie()
    name_list, courseid_list, classid_list = get_course_class_id()
    while True:
        name, signID, sign_type = get_sign_list(name_list, courseid_list, classid_list)
        # 获取到了最新签到的id则提交给sign，没有获取到(False)则继续尝试获取
        # 230302普通签到signtype改为了0  删去相关判定
        if name and signID:
            sign(name, signID, sign_type)
            break
        # 延迟一定时间后继续扫描
        else:
            # 设置一个浮动值尽可能避开检测
            scan_gap_time = userinfo['conf']['scan_gap_time'] + random.uniform(-1, 1)
            time.sleep(scan_gap_time)


if __name__ == '__main__':
    main_handler(1, 2)
