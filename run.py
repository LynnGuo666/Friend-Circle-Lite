import logging
import json
import sys
import os
import requests
import datetime

from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time, marge_data_from_json_url, marge_errors_from_json_url, deal_with_large_data, check_feed, parse_feed
from friend_circle_lite.get_conf import load_config
from rss_subscribe.push_article_update import get_latest_articles_from_link, extract_emails_from_issues
from push_rss_update.send_email import send_emails

# 日志记录
logging.basicConfig(level=logging.INFO, format='😋 %(levelname)s: %(message)s')

# 爬虫部分内容
config = load_config("./conf.yaml")
if config["spider_settings"]["enable"]:
    logging.info("爬虫已启用")
    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    specific_RSS = config['specific_RSS']
    logging.info("正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章".format(json_url=json_url, article_count=article_count))
    
    # 获取并��理数据
    response = requests.get(json_url)
    friends_data = response.json()
    
    # 处理新的 JSON 格式
    friends = friends_data['content']
    result = {
        'statistical_data': {
            'friends_num': len(friends),
            'active_num': 0,
            'error_num': 0,
            'article_num': 0,
            'last_updated_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        'article_data': []
    }
    lost_friends = []

    for friend in friends:
        name = friend['title']
        blog_url = friend['url']
        avatar = friend['avatar']
        feed_type, feed_url = check_feed(blog_url, requests.Session())
        if feed_type != 'none':
            feed_info = parse_feed(feed_url, requests.Session(), article_count, blog_url)
            articles = [
                {
                    'title': article['title'],
                    'created': article['published'],
                    'link': article['link'],
                    'author': name,
                    'avatar': avatar
                }
                for article in feed_info['articles']
            ]
            result['article_data'].extend(articles)
            result['statistical_data']['active_num'] += 1
            result['statistical_data']['article_num'] += len(articles)
        else:
            lost_friends.append(friend)
            result['statistical_data']['error_num'] += 1

    if config["spider_settings"]["merge_result"]["enable"]:
        marge_json_url = config['spider_settings']["merge_result"]['merge_json_url']
        logging.info("合并数据功能开启，从 {marge_json_url} 中获取境外数据并合并".format(marge_json_url=marge_json_url + "/all.json"))
        result = marge_data_from_json_url(result, marge_json_url + "/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, marge_json_url + "/errors.json")
    
    logging.info("数据获取完毕，目前共有 {count} 位好友的动态，正在处理数据".format(count=len(result.get("article_data", []))))
    result = deal_with_large_data(result)
    
    # 保存结果
    output_data = {
        "friends": [
            [friend['title'], friend['url'], friend['avatar']] for friend in friends
        ]
    }
    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(lost_friends, f, ensure_ascii=False, indent=2)

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    logging.info("推送功能已启用，正在准备推送，获取配置信息")
    email_settings = config["smtp"]
    email = email_settings["email"]
    server = email_settings["server"]
    port = email_settings["port"]
    use_tls = email_settings["use_tls"]
    password = os.getenv("SMTP_PWD")
    logging.info("SMTP 服务器信息：{server}:{port}".format(server=server, port=port))
    logging.info("密码：{pwd}************".format(pwd=password[:3]))

if config["email_push"]["enable"]:
    logging.info("邮件推送已启用")
    logging.info("抱歉，目前暂未实现功能")
    
if config["rss_subscribe"]["enable"]:
    logging.info("RSS 订阅推送已启用")
    # 获取并强制转换为字符串
    # 尝试从环境变量获取 FCL_REPO
    fcl_repo = os.getenv('FCL_REPO')

    # 提取 github_username 和 github_repo
    if fcl_repo:
        github_username, github_repo = fcl_repo.split('/')
    else:
        github_username = str(config["rss_subscribe"]["github_username"]).strip()
        github_repo = str(config["rss_subscribe"]["github_repo"]).strip()
    
    # 输出 github_username 和 github_repo
    logging.info("github_username: {github_username}".format(github_username=github_username))
    logging.info("github_repo: {github_repo}".format(github_repo=github_repo))
    
    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    email_template = config["rss_subscribe"]["email_template"]
    # 获取网站信息
    website_title = config["rss_subscribe"]["website_info"]["title"]
    # 获取最近更新的文章
    latest_articles = get_latest_articles_from_link(
        url=your_blog_url,
        count=5,
        last_articles_path="./rss_subscribe/last_articles.json"
        )
    logging.info("获取到的最新文章为：{latest_articles}".format(latest_articles=latest_articles))
    if latest_articles == None:
        logging.info("无未进行推送的新文章")
    else:
        github_api_url = "https://api.github.com/repos/" + github_username + "/" + github_repo + "/issues" + "?state=closed&label=subscribed&per_page=200"
        logging.info("正在从 {github_api_url} 中获取订阅信息".format(github_api_url=github_api_url))
        email_list = extract_emails_from_issues(github_api_url)
        if email_list == None:
            logging.info("无邮箱列表，请检查您的订阅列表是否有订阅者或订阅格式是否正确")
            sys.exit(0)
        else:
            logging.info("获取到的邮箱列表为：{email_list}".format(email_list=email_list))
        # 循环latest_articles，发送邮件
        for article in latest_articles:
            template_data = {
                "title": article["title"],
                "summary": article["summary"],
                "published": article["published"],
                "link": article["link"],
                "website_title": website_title,
                "github_issue_url": f"https://github.com/{github_username}/{github_repo}/issues?q=is%3Aissue+is%3Aclosed",
            }
            
            send_emails(
                emails=email_list["emails"],
                sender_email=email,
                smtp_server=server,
                port=port,
                password=password,
                subject= website_title + "の最新文章：" + article["title"],
                body="文章链接：" + article["link"] + "\n" + "文章内容：" + article["summary"] + "\n" + "发布时间：" + article["published"],
                template_path=email_template,
                template_data=template_data,
                use_tls=use_tls
            )
