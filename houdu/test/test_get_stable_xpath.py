from lxml import etree
from typing import Optional


def has_ancestor_tag(node: etree._Element, tag_name: str) -> bool:
    """
    检查节点的祖先路径中是否包含指定标签

    参数：
        node: lxml元素节点
        tag_name: 要检查的标签名（如 'table', 'form', 'iframe'）

    返回值：
        bool: True表示路径中包含该标签，False表示不包含
    """
    if not isinstance(node, etree._Element):
        return False

    tag_name_lower = tag_name.lower()
    current = node

    while current is not None:
        # 获取标签名并处理命名空间
        tag = current.tag
        if isinstance(tag, str):
            if '}' in tag:
                tag = tag.split('}')[-1]
            if tag.lower() == tag_name_lower:
                return True
        current = current.getparent()

    return False


def is_in_table(node: etree._Element) -> bool:
    """
    检查节点是否在表格(table)元素内

    参数：
        node: lxml元素节点

    返回值：
        bool: True表示在表格内，False表示不在表格内
    """
    return has_ancestor_tag(node, 'table')


def get_parent_table(node: etree._Element) -> Optional[etree._Element]:
    """
    如果节点是td元素，返回其往上的第一个table祖先节点

    参数：
        node: lxml元素节点

    返回值：
        如果节点是td且存在父级table，返回table元素节点
        如果节点不是td或不存在父级table，返回None
    """
    if not isinstance(node, etree._Element):
        return None

    # 检查当前节点是否是td元素
    tag = node.tag
    if isinstance(tag, str):
        if '}' in tag:
            tag = tag.split('}')[-1]
        if tag.lower() != 'td':
            # 不是td元素，直接返回None
            return None

    # 是td元素，向上查找第一个table节点
    current = node.getparent()
    while current is not None:
        current_tag = current.tag
        if isinstance(current_tag, str):
            if '}' in current_tag:
                current_tag = current_tag.split('}')[-1]
            if current_tag.lower() == 'table':
                return current
        current = current.getparent()

    return None


def get_stable_xpath(node: etree._Element) -> Optional[tuple[str, bool]]:
    """
    获取HTML节点的稳定XPath路径（贴合CSS选择器风格）
    - 有id：标签名#id值（如 table#main-table）
    - 无id有class：标签名.class1.class2（如 tr.row.normal）
    - 无id/class：标签名[序号]（如 td[2]）

    返回值：
        tuple[str, bool]: (xpath路径, 是否使用了索引)
        - xpath路径：生成的XPath字符串
        - 是否使用了索引：True表示路径中包含索引（稳定性较差），False表示仅使用id/class（稳定性较好）
        - 如果处理失败返回None
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
    used_index = False  # 标记是否使用了索引

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
        # 3.1 优先使用id（#拼接），但需检测冲突
        node_id = current_node.get('id', '').strip()
        if node_id:
            # 检测同级是否有相同id的元素（避免不规范HTML的重复id）
            parent = current_node.getparent()
            has_id_conflict = False
            if parent is not None:
                same_id_siblings = []
                for child in parent.iterchildren():
                    if not isinstance(child, etree._Element) or child.tag in (etree.Comment, etree.ProcessingInstruction):
                        continue
                    # 比较标签名和id属性
                    child_tag = child.tag
                    if isinstance(child_tag, str) and '}' in child_tag:
                        child_tag = child_tag.split('}')[-1]
                    if child_tag.lower() == tag and child.get('id', '').strip() == node_id:
                        same_id_siblings.append(child)
                # 如果有多个相同id的同级元素，则存在冲突
                if len(same_id_siblings) > 1:
                    has_id_conflict = True

            if has_id_conflict:
                # id冲突，降级到class检测
                xpath_part = None
            else:
                # 无冲突，使用id
                xpath_part = f"{tag}#{node_id}"
        else:
            xpath_part = None

        # 3.2 无id或id冲突时使用class（.拼接多个class），但需检测冲突
        if xpath_part is None:
            node_class = current_node.get('class', '').strip()
            if node_class:
                # 拆分class并过滤空值（处理多个class/多余空格）
                class_list = [cls.strip() for cls in node_class.split() if cls.strip()]
                if class_list:  # 确保有有效class
                    class_selector = '.' + '.'.join(class_list)
                    xpath_part_candidate = f"{tag}{class_selector}"

                    # 检测同级是否有相同class的元素（避免重复）
                    parent = current_node.getparent()
                    has_conflict = False
                    if parent is not None:
                        same_class_siblings = []
                        for child in parent.iterchildren():
                            if not isinstance(child, etree._Element) or child.tag in (etree.Comment, etree.ProcessingInstruction):
                                continue
                            # 比较标签名和class属性
                            child_tag = child.tag
                            if isinstance(child_tag, str) and '}' in child_tag:
                                child_tag = child_tag.split('}')[-1]
                            if child_tag.lower() == tag and child.get('class', '').strip() == node_class:
                                same_class_siblings.append(child)
                        # 如果有多个相同class的同级元素，则存在冲突
                        if len(same_class_siblings) > 1:
                            has_conflict = True

                    if has_conflict:
                        # 有冲突，降级到索引
                        xpath_part = None
                    else:
                        # 无冲突，使用class
                        xpath_part = xpath_part_candidate
                else:
                    # 无有效class，降级到索引
                    xpath_part = None
            else:
                # 无class，降级到索引
                xpath_part = None

            # 3.3 无id/class或有冲突时使用索引兜底
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
                        used_index = True  # 标记使用了索引
                    except ValueError:
                        xpath_part = f"{tag}[1]"
                        used_index = True  # 标记使用了索引

        xpath_parts.append(xpath_part)
        current_node = current_node.getparent()

    # 4. 拼接最终XPath路径
    if xpath_parts:
        xpath_parts.reverse()
        full_xpath = '/' + '/'.join(xpath_parts)
        return (full_xpath, used_index)
    return None

# ------------------- 测试函数 -------------------
def test_basic_xpath():
    """测试1-4：基础XPath生成（id、class、索引、空格处理）"""
    print("=== 测试1-4：基础XPath生成 ===")

    test_html = """
    <html>
      <body>
        <table id="main-table">
          <tr class="row normal active">
            <td>无属性</td>
            <td class="cell target">目标单元格</td>
          </tr>
        </table>
        <div class="sidebar  ">侧边栏</div>
      </body>
    </html>
    """
    tree = etree.HTML(test_html)

    # 测试1：有class的td节点
    target_node1 = tree.xpath('//td[@class="cell target"]')[0]
    xpath1, used_index1 = get_stable_xpath(target_node1)
    print(f"有class节点的XPath：{xpath1}, 使用索引：{used_index1}")

    # 测试2：多class的tr节点
    target_node2 = tree.xpath('//tr')[0]
    xpath2, used_index2 = get_stable_xpath(target_node2)
    print(f"多class节点的XPath：{xpath2}, 使用索引：{used_index2}")

    # 测试3：无id/class的td节点
    target_node3 = tree.xpath('//td[1]')[0]
    xpath3, used_index3 = get_stable_xpath(target_node3)
    print(f"无属性节点的XPath：{xpath3}, 使用索引：{used_index3}")

    # 测试4：含多余空格class的div节点
    target_node4 = tree.xpath('//div')[0]
    xpath4, used_index4 = get_stable_xpath(target_node4)
    print(f"含空格class的div节点XPath：{xpath4}, 使用索引：{used_index4}")


def test_class_conflict():
    """测试5：class冲突检测"""
    print("\n=== 测试5：验证class冲突检测 ===")

    test_html_conflict = """
    <html>
      <body>
        <div id="container">
          <p class="text highlight">段落1</p>
          <p class="text highlight">段落2</p>
          <p class="text highlight">段落3</p>
          <p class="different">段落4（不同class）</p>
        </div>
      </body>
    </html>
    """
    tree_conflict = etree.HTML(test_html_conflict)

    # 测试：三个相同class的p元素应该使用索引而非class
    p_nodes = tree_conflict.xpath('//p[@class="text highlight"]')
    for i, node in enumerate(p_nodes, 1):
        xpath, used_index = get_stable_xpath(node)
        print(f"段落{i}的XPath：{xpath}, 使用索引：{used_index}")

    # 测试：唯一class的p元素应该使用class
    p_different = tree_conflict.xpath('//p[@class="different"]')[0]
    xpath_different, used_index_different = get_stable_xpath(p_different)
    print(f"唯一class段落的XPath：{xpath_different}, 使用索引：{used_index_different}")


def test_id_conflict():
    """测试6：id冲突检测"""
    print("\n=== 测试6：验证id冲突检测 ===")

    test_html_id_conflict = """
    <html>
      <body>
        <div id="wrapper">
          <span id="item">项目1</span>
          <span id="item">项目2（重复id）</span>
          <span id="item" class="special">项目3（重复id+class）</span>
          <span id="unique">项目4（唯一id）</span>
        </div>
      </body>
    </html>
    """
    tree_id = etree.HTML(test_html_id_conflict)

    # 测试：重复id的元素应该降级到class或索引
    spans = tree_id.xpath('//span')
    for i, node in enumerate(spans, 1):
        xpath, used_index = get_stable_xpath(node)
        node_id = node.get('id', '')
        node_class = node.get('class', '')
        print(f"项目{i} (id={node_id}, class={node_class}): {xpath}, 使用索引：{used_index}")


def test_table_detection():
    """测试7：表格检测功能"""
    print("\n=== 测试7：验证表格检测功能 ===")

    test_html_table = """
    <html>
      <body>
        <div id="content">
          <p class="intro">这是段落（不在表格内）</p>
          <table id="data-table">
            <tr>
              <td class="cell">单元格1</td>
              <td class="cell">单元格2</td>
            </tr>
          </table>
          <form>
            <table id="form-table">
              <tr>
                <td>表单内的表格</td>
              </tr>
            </table>
            <input type="text" name="username">
          </form>
        </div>
      </body>
    </html>
    """
    tree_table = etree.HTML(test_html_table)

    # 测试1：段落不在表格内
    p_node = tree_table.xpath('//p[@class="intro"]')[0]
    xpath_p, used_index_p = get_stable_xpath(p_node)
    in_table_p = is_in_table(p_node)
    print(f"段落节点: {xpath_p}")
    print(f"  在表格内: {in_table_p}, 使用索引: {used_index_p}")

    # 测试2：td单元格在表格内
    td_nodes = tree_table.xpath('//td[@class="cell"]')
    for i, td in enumerate(td_nodes, 1):
        xpath_td, used_index_td = get_stable_xpath(td)
        in_table_td = is_in_table(td)
        print(f"单元格{i}: {xpath_td}")
        print(f"  在表格内: {in_table_td}, 使用索引: {used_index_td}")

    # 测试3：嵌套在form中的table里的td
    td_form = tree_table.xpath('//form//td')[0]
    xpath_form_td, used_index_form_td = get_stable_xpath(td_form)
    in_table_form_td = is_in_table(td_form)
    in_form = has_ancestor_tag(td_form, 'form')
    print(f"表单内单元格: {xpath_form_td}")
    print(f"  在表格内: {in_table_form_td}, 在表单内: {in_form}, 使用索引: {used_index_form_td}")

    # 测试4：input不在表格内但在form内
    input_node = tree_table.xpath('//input')[0]
    xpath_input, used_index_input = get_stable_xpath(input_node)
    in_table_input = is_in_table(input_node)
    in_form_input = has_ancestor_tag(input_node, 'form')
    print(f"输入框: {xpath_input}")
    print(f"  在表格内: {in_table_input}, 在表单内: {in_form_input}, 使用索引: {used_index_input}")


def test_get_parent_table():
    """测试8：get_parent_table功能"""
    print("\n=== 测试8：验证get_parent_table功能 ===")

    test_html_nested = """
    <html>
      <body>
        <div id="wrapper">
          <p>段落（非td）</p>
          <table id="outer-table" class="main">
            <tr>
              <td id="outer-cell">外层单元格</td>
              <td>
                <table id="inner-table" class="nested">
                  <tr>
                    <td id="inner-cell">嵌套单元格</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """
    tree_nested = etree.HTML(test_html_nested)

    # 测试1：非td元素应该返回None
    p_element = tree_nested.xpath('//p')[0]
    parent_table_p = get_parent_table(p_element)
    print(f"段落元素: parent_table = {parent_table_p}")

    # 测试2：外层td返回外层table
    outer_td = tree_nested.xpath('//td[@id="outer-cell"]')[0]
    parent_table_outer = get_parent_table(outer_td)
    if parent_table_outer is not None:
        table_id = parent_table_outer.get('id', '')
        table_class = parent_table_outer.get('class', '')
        print(f"外层td元素: parent_table id={table_id}, class={table_class}")
    else:
        print(f"外层td元素: parent_table = None")

    # 测试3：嵌套td返回最近的table（内层table）
    inner_td = tree_nested.xpath('//td[@id="inner-cell"]')[0]
    parent_table_inner = get_parent_table(inner_td)
    if parent_table_inner is not None:
        table_id = parent_table_inner.get('id', '')
        table_class = parent_table_inner.get('class', '')
        print(f"嵌套td元素: parent_table id={table_id}, class={table_class}")
    else:
        print(f"嵌套td元素: parent_table = None")

    # 测试4：验证返回的是table节点本身
    if parent_table_inner is not None:
        xpath_table, _ = get_stable_xpath(parent_table_inner)
        print(f"返回的table节点路径: {xpath_table}")


# ------------------- 主测试入口 -------------------
if __name__ == "__main__":
    test_basic_xpath()
    test_class_conflict()
    test_id_conflict()
    test_table_detection()
    test_get_parent_table()