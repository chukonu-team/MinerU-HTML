from lxml import etree
from typing import Optional

def get_stable_xpath(node: etree._Element) -> Optional[str]:
    """
    获取HTML节点的稳定XPath路径（贴合CSS选择器风格）
    - 有id：标签名#id值（如 table#main-table）
    - 无id有class：标签名.class1.class2（如 tr.row.normal）
    - 无id/class：标签名[序号]（如 td[2]）
    """
    # 1. 基础校验：仅处理合法的元素节点
    if not isinstance(node, etree._Element):
        print("错误：输入不是有效的lxml元素节点对象")
        return None
    if node.tag in (etree.Comment, etree.ProcessingInstruction, etree.Entity):
        print("错误：不支持注释/文本/处理指令等非元素节点")
        return None

    xpath_parts = []
    current_node = node

    while current_node is not None:
        # 2. 安全获取标签名（处理命名空间、转小写）
        tag = current_node.tag
        if not isinstance(tag, str):
            print(f"警告：节点标签不是字符串类型，跳过该节点")
            break
        if '}' in tag:
            tag = tag.split('}')[-1]
        tag = tag.lower()

        # 3. 生成路径片段（优先级：id > class > 索引）
        xpath_part = ""
        # 3.1 优先使用id（#拼接）
        node_id = current_node.get('id', '').strip()
        if node_id:
            xpath_part = f"{tag}#{node_id}"
        # 3.2 无id时使用class（.拼接多个class）
        else:
            node_class = current_node.get('class', '').strip()
            if node_class:
                # 拆分class并过滤空值（处理多个class/多余空格）
                class_list = [cls.strip() for cls in node_class.split() if cls.strip()]
                if class_list:  # 确保有有效class
                    class_selector = '.' + '.'.join(class_list)
                    xpath_part = f"{tag}{class_selector}"
                else:
                    # 无有效class，降级到索引
                    xpath_part = None
            else:
                # 无class，降级到索引
                xpath_part = None

            # 3.3 无id/class时使用索引兜底
            if xpath_part is None:
                parent = current_node.getparent()
                if parent is None:
                    xpath_part = tag
                else:
                    # 统计父节点下同标签名的元素节点（排除非元素节点）
                    same_tag_siblings = []
                    for child in parent.iterchildren():
                        if not isinstance(child, etree._Element) or child.tag in (etree.Comment, etree.ProcessingInstruction):
                            continue
                        child_tag = child.tag
                        if isinstance(child_tag, str) and '}' in child_tag:
                            child_tag = child_tag.split('}')[-1]
                        if child_tag.lower() == tag:
                            same_tag_siblings.append(child)
                    # 计算索引（容错：节点不在列表时默认1）
                    try:
                        node_index = same_tag_siblings.index(current_node) + 1
                        xpath_part = f"{tag}[{node_index}]"
                    except ValueError:
                        xpath_part = f"{tag}[1]"

        xpath_parts.append(xpath_part)
        current_node = current_node.getparent()

    # 4. 拼接最终XPath路径
    if xpath_parts:
        xpath_parts.reverse()
        full_xpath = '/' + '/'.join(xpath_parts)
        return full_xpath
    return None

# ------------------- 测试示例 -------------------
if __name__ == "__main__":
    # 包含id、多class、无属性的混合场景
    test_html = """
    <html>
      <body>
        <table id="main-table">  <!-- 有id → table#main-table -->
          <tr class="row normal active">  <!-- 多class → tr.row.normal.active -->
            <td>无属性</td>  <!-- 无id/class → td[1] -->
            <td class="cell target">目标单元格</td>  <!-- 有class → td.cell.target -->
          </tr>
        </table>
        <div class="sidebar  ">侧边栏</div>  <!-- 含空格class → div.sidebar -->
      </body>
    </html>
    """

    # 解析HTML
    tree = etree.HTML(test_html)

    # 测试1：有class的td节点
    target_node1 = tree.xpath('//td[@class="cell target"]')[0]
    xpath1 = get_stable_xpath(target_node1)
    print("有class节点的XPath：", xpath1)
    # 输出：/html/body/table#main-table/tr.row.normal.active/td.cell.target

    # 测试2：多class的tr节点
    target_node2 = tree.xpath('//tr')[0]
    xpath2 = get_stable_xpath(target_node2)
    print("多class节点的XPath：", xpath2)
    # 输出：/html/body/table#main-table/tr.row.normal.active

    # 测试3：无id/class的td节点
    target_node3 = tree.xpath('//td[1]')[0]
    xpath3 = get_stable_xpath(target_node3)
    print("无属性节点的XPath：", xpath3)
    # 输出：/html/body/table#main-table/tr.row.normal.active/td[1]

    # 测试4：含多余空格class的div节点
    target_node4 = tree.xpath('//div')[0]
    xpath4 = get_stable_xpath(target_node4)
    print("含空格class的div节点XPath：", xpath4)
    # 输出：/html/body/div.sidebar