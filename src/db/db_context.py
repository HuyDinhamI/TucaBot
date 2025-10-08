# import time
# import logging
# import json
# import mysql.connector
# from src.settings import settings
# from src.common.constants import AgentType

# logger = logging.getLogger(__name__)


# class DBManager:
#     def __init__(self):
#         self.config = {
#             "host": settings.MYSQL_CONF["connection"]["host"],
#             "user": settings.MYSQL_CONF["connection"]["user"],
#             "password": settings.MYSQL_CONF["connection"]["password"],
#             "database": settings.MYSQL_CONF["connection"]["database"],
#         }

#     """
#     Khởi tạo kết nối MySQL
#     """
#     def _connect_to_mysql(self, attempts=2, delay=1):
#         attempt = 1
#         # Implement a reconnection routine
#         while attempt < attempts + 1:
#             try:
#                 return mysql.connector.connect(**self.config)
#             except (mysql.connector.Error, IOError) as err:
#                 if attempts is attempt:
#                     # Attempts to reconnect failed; returning None
#                     logger.info(
#                         "Failed to connect, exiting without a connection: %s", err
#                     )
#                     return None
#                 logger.info(
#                     "Connection failed: %s. Retrying (%d/%d)...",
#                     err,
#                     attempt,
#                     attempts - 1,
#                 )
#                 # progressive reconnect delay
#                 time.sleep(delay**attempt)
#                 attempt += 1
#         return None

#     """
#     Lấy cấu hình của agent từ database theo agent_id
#     agent_config: {
#         agent_id: "agent_id",
#         name: "abc",
#         type: "single_agent",
#         nodes: {
#             llm: {
#                 model: "gpt-4o"
#                 temperature: 0,
#                 max_turns: 15,
#                 system_prompt: "Hello, I am a chatbot. I am here to help you with your queries. Please ask me anything.",
#                 provider: openai
#             }
#             search: {
#                 "top_k": top_k, # 5
#                 "score_threshold": score_threshold, # 0.5
#                 "env": "development", # production or development
#             }
#         }
#     }
#     """

#     def _get_agent_config(self, agent_id: str):
#         query = """select ac.AppId, a.Name, a.AppType, ac.Model, ac.PrePrompt, ac.Tools, ac.Agents
#                     from app as a inner join app_config as ac 
#                     on a.Id = ac.AppId 
#                     where a.Id = %s """
#         cnx = self._connect_to_mysql()
#         if cnx and cnx.is_connected():
#             with cnx.cursor(dictionary=True) as cursor:
#                 cursor.execute(query, (agent_id,))
#                 result = cursor.fetchone()
#             cnx.close()
#             if result:
#                 agent_type = result["AppType"]

#                 llm = {}
#                 if result["Model"]:
#                     llm = json.loads(result["Model"])
#                     if result["PrePrompt"]:
#                         llm.update({
#                             "system_prompt": result["PrePrompt"]
#                         })

#                 agent_config = {
#                     "agent_id": result["AppId"],
#                     "name ": result["Name"],
#                     "type": agent_type,
#                     "nodes": {
#                         "llm": llm,
#                         "tools": json.loads(result["Tools"]) if result["Tools"] else []
#                     }
#                 }

#                 if agent_type in AgentType.MULTI.value:
#                     agent_config.update({
#                         "agents": json.loads(result["Agents"]) if result["Agents"] else []
#                     })

#                 return agent_config
#             return None
#         else:
#             logger.error("Could not connect msql")
#             return None
