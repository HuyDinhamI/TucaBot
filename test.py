# #!/usr/bin/env python3
# import requests
# import sys

# def list_indices(es_url):
#     """
#     Liệt kê tất cả index trên Elasticsearch.
#     """
#     try:
#         r = requests.get(f"{es_url}/_cat/indices?h=index", timeout=10)
#         r.raise_for_status()
#         indices = r.text.strip().split("\n")
#         print("Các index trên Elasticsearch:")
#         for idx in indices:
#             print(f"- {idx}")
#     except requests.exceptions.RequestException as e:
#         print(f"Lỗi khi kết nối Elasticsearch: {e}", file=sys.stderr)

# if __name__ == "__main__":
#     # URL Elasticsearch, ví dụ http://localhost:9200
#     es_url = "http://103.90.224.126:9200"
#     list_indices(es_url)

#!/usr/bin/env python3
# import requests
# import sys

# def delete_index(es_url, index_name):
#     """
#     Xóa index trên Elasticsearch.
#     """
#     try:
#         r = requests.delete(f"{es_url}/{index_name}", timeout=10)
#         r.raise_for_status()
#         print(f"Index '{index_name}' đã được xóa thành công.")
#     except requests.exceptions.RequestException as e:
#         print(f"Lỗi khi xóa index: {e}", file=sys.stderr)

# if __name__ == "__main__":
#     es_url = "http://103.90.224.126:9200"
#     index_name = "mavap"
#     delete_index(es_url, index_name)


#!/usr/bin/env python3
import requests
import sys
import json

def preview_index(es_url, index_name, size=5):
    """
    Xem trước dữ liệu trong index.
    size: số lượng document muốn xem
    """
    try:
        query = {
            "size": size,
            "query": {
                "match_all": {}
            }
        }
        r = requests.get(f"{es_url}/{index_name}/_search", headers={"Content-Type": "application/json"}, data=json.dumps(query))
        r.raise_for_status()
        results = r.json()
        hits = results.get("hits", {}).get("hits", [])
        if not hits:
            print(f"Index '{index_name}' không có dữ liệu.")
        else:
            print(f"Hiển thị {len(hits)} document đầu tiên trong index '{index_name}':\n")
            for hit in hits:
                print(json.dumps(hit["_source"], indent=2, ensure_ascii=False))
                print("-" * 50)
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy vấn index: {e}", file=sys.stderr)

if __name__ == "__main__":
    es_url = "http://103.90.224.126:9200"
    index_name = "mavap"
    preview_index(es_url, index_name)
